# Miền giá trị, kích thước đầu vào và ràng buộc tài nguyên

Khi đặc tả một thuật toán, câu hỏi “đầu vào là gì?” chưa đủ. Cần biết **mỗi giá trị có thể nằm trong miền nào**, **đầu vào có thể lớn đến đâu** và **chương trình được phép dùng bao nhiêu thời gian, bộ nhớ và ngăn xếp**. Ba nhóm thông tin này quyết định kiểu dữ liệu, tính đúng đắn, cấu trúc dữ liệu và phương án thuật toán khả thi.

## 1. Phân biệt đề bài, miền hợp lệ và giới hạn thực thi

Một đặc tả hữu ích gồm bốn phần liên hệ với nhau:

1. **Dữ liệu và ngữ nghĩa:** đầu vào chứa gì (mảng số, chuỗi, đồ thị, ma trận...), các phần tử biểu diễn điều gì, đầu ra phải thỏa điều kiện nào.
2. **Miền giá trị (value domain):** mỗi biến được phép nhận những giá trị nào, ví dụ `1 ≤ n ≤ 200_000`, `−10^9 ≤ a[i] ≤ 10^9`, trọng số cạnh có âm hay không, chuỗi có ký tự Unicode hay chỉ ASCII.
3. **Kích thước đầu vào (input size):** số phần tử, đỉnh, cạnh, truy vấn, trường hợp kiểm thử, tổng số ký tự hoặc số bit cần xử lý. Đây là các tham số chi phối độ phức tạp.
4. **Ràng buộc tài nguyên (resource constraints):** thời gian chạy, bộ nhớ tối đa, giới hạn ngăn xếp, giới hạn I/O hoặc kích thước đầu ra.

Ví dụ, yêu cầu “tìm tổng lớn nhất của một dãy con liên tiếp không rỗng” xác định **đáp án cần tính**. Điều kiện `1 ≤ n ≤ 200_000` và `−10^9 ≤ a[i] ≤ 10^9` xác định **những dữ liệu thuật toán phải xử lý đúng**. Giới hạn bộ nhớ hoặc thời gian của môi trường chạy xác định **cách triển khai có khả thi không**. Không nên trộn ba loại ràng buộc này với nhau.

Trong bài toán có đầu vào được bảo đảm hợp lệ, thuật toán được phép dựa vào bảo đảm đó. Khi xây dựng API hoặc hệ thống nhận dữ liệu không đáng tin, cần kiểm tra và xử lý đầu vào nằm ngoài miền đã công bố. Đây là khác biệt về **hợp đồng đầu vào**, không phải lý do để mặc định mọi đề bài đều phải đọc dữ liệu lỗi.

## 2. Mô tả miền giá trị chính xác

Một khoảng số mới chỉ là một phần của miền hợp lệ. Khi đọc hoặc viết đặc tả, hãy làm rõ:

- **Kiểu và biên:** số nguyên/số thực; có âm, có số 0 không; cận dưới/cận trên có được lấy bằng không; kiểu có dấu hay không dấu.
- **Cấu trúc:** mảng được sắp xếp chưa; phần tử có thể trùng không; đồ thị có hướng hay vô hướng; có tự khuyên, đa cạnh, chu trình không; ma trận có thể rỗng không.
- **Quan hệ giữa biến:** `0 ≤ m ≤ n(n−1)/2` chỉ đúng với đồ thị vô hướng đơn, không tự khuyên; với loại đồ thị khác, cận của `m` có thể khác.
- **Ràng buộc tổng hợp:** `Σ n_i ≤ 200_000` trên mọi test khác hẳn việc mỗi test có `n_i ≤ 200_000` nhưng tổng không bị chặn.
- **Ngữ nghĩa đầu ra:** được trả về một hay nhiều nghiệm; nếu không có nghiệm thì trả gì; có bắt buộc ổn định thứ tự, chính xác tuyệt đối hay chấp nhận sai số.

Ví dụ “hai con trỏ trên mảng đã sắp xếp” cần bảo đảm **thứ tự không giảm**. Nếu đầu vào chưa sắp xếp, phải sắp xếp hoặc thay đổi thuật toán. “Cửa sổ trượt để tìm đoạn có tổng không vượt `S`” thường dùng tính đơn điệu khi phần tử **không âm**; nếu xuất hiện số âm, việc mở rộng cửa sổ có thể làm tổng giảm, nên chứng minh và thuật toán cũ có thể không còn đúng.

Trong bài toán chuỗi, “độ dài” cũng phải được định nghĩa: số byte UTF-8, số đơn vị mã UTF-16, số code point Unicode hay số ký tự người dùng nhìn thấy là các đại lượng khác nhau. Với Java, `String.length()` trả số **đơn vị mã UTF-16**, không nhất thiết bằng số code point.

## 3. Kích thước đầu vào là một bộ tham số

Ký hiệu cần gắn với đúng cấu trúc:

| Dữ liệu | Tham số hữu ích | Ý nghĩa |
|---|---|---|
| Mảng/danh sách | `n` | Số phần tử, không phải độ lớn của từng phần tử |
| Ma trận/lưới | `r, c` | Số ô `r·c`; lưu toàn lưới thường tốn `O(r·c)` |
| Đồ thị | `V, E` | Số đỉnh và số cạnh; `O(V+E)` khác `O(V²)` |
| Nhiều truy vấn | `n, Q` | Chi phí tiền xử lý và tổng chi phí của `Q` truy vấn |
| Nhiều bộ kiểm thử | `T, Σn_i, Σm_i` | Tổng công việc qua tất cả các bộ dữ liệu |
| Chuỗi/tệp | `L` | Số đơn vị được đặc tả: byte, code point, ký tự... |
| Số nguyên rất lớn | `B` | Số bit của toán hạng; cộng/nhân không còn mặc định là `O(1)` trên số có độ dài tùy ý |

**Miền giá trị và kích thước là hai trục khác nhau.** Mảng có `n = 10^5` phần tử nhưng `a[i]` chỉ trong `0..100` có thể phù hợp với bảng đếm. Mảng chỉ có `n = 10^3` phần tử nhưng mỗi số dài hàng nghìn chữ số cần tính cả chi phí phép toán trên số lớn.

Với đồ thị thưa (`E` gần cùng bậc với `V`), danh sách kề thường tiết kiệm bộ nhớ hơn ma trận kề. Với đồ thị dày đặc, lựa chọn có thể khác. Cần cân nhắc cả thao tác chính: tra cứu một cạnh, duyệt láng giềng, thêm/xóa cạnh hay chạy thuật toán đường đi.

## 4. Suy ra giới hạn số học trước khi chọn kiểu dữ liệu

Một sai lầm phổ biến là chỉ xét miền của **một phần tử** mà bỏ qua miền của **biểu thức trung gian và kết quả**.

Giả sử `1 ≤ n ≤ 200_000` và `−10^9 ≤ a[i] ≤ 10^9`. Mỗi phần tử vừa trong `int` Java, nhưng tổng `n` phần tử có thể đạt trị tuyệt đối `200_000 × 10^9 = 2 × 10^14`. Vì thế, biến tổng và các giá trị tổng trung gian cần `long`.

| Kiểu trong Java | Miền số nguyên | Tình huống |
|---|---|---|
| `int` (32 bit, có dấu) | `−2^31 .. 2^31−1` | Chỉ số, đếm/số liệu nằm trong miền |
| `long` (64 bit, có dấu) | `−2^63 .. 2^63−1` | Tổng, tích hoặc trọng số tích lũy lớn hơn `int` |
| `BigInteger` | Độ chính xác nguyên tùy ý, bị giới hạn bởi tài nguyên | Kết quả có thể vượt cả `long` |

Các quy tắc thực hành:

- Xác định cận của **từng phép cộng, trừ, nhân, tổng tiền tố, số cặp**. Ví dụ, số cặp của `n` phần tử là `n(n−1)/2`; với `n = 100_000`, kết quả là `4_999_950_000`, vượt `int`.
- **Mở rộng kiểu trước phép toán:** dùng `(long) a * b`, không dùng `(long) (a * b)` khi `a` và `b` là `int`; biểu thức trong ngoặc thứ hai đã có thể tràn trước khi ép kiểu.
- `long total = 0; total += x;` là an toàn khi đã chứng minh cận tổng nằm trong `long`. Chuyển sang `long` không tự động giải quyết mọi bài; `long` vẫn có thể tràn.
- Khi cần phát hiện tràn thay vì tự chứng minh cận, Java có `Math.addExact`, `Math.multiplyExact` và `Math.subtractExact`; các hàm này ném `ArithmeticException` nếu tràn.
- `Math.abs(Integer.MIN_VALUE)` vẫn trả về giá trị âm do không có số dương tương ứng trong `int`. Với toán hạng `int`, có thể chuyển sang `long` trước khi lấy trị tuyệt đối; `Long.MIN_VALUE` vẫn cần xử lý riêng.
- Với tính toán tiền, không tự động chọn `double` nếu cần biểu diễn thập phân chính xác; cân nhắc số nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` theo hợp đồng bài toán.

Miền còn quyết định điều kiện hợp lệ của phép toán: chia cần tránh mẫu số 0; căn bậc hai thực yêu cầu đối số không âm; chỉ số mảng phải thuộc `0..n−1`; phép lấy dư trong Java với số âm có thể cho kết quả âm (`−5 % 3 == −2`). Nếu cần phần dư không âm với mô-đun dương, sử dụng `Math.floorMod` khi phù hợp.

## 5. Đọc ràng buộc thời gian như một bài toán độ phức tạp

Không có ngưỡng phổ quát rằng “một giây xử lý được bao nhiêu phép toán”: tốc độ phụ thuộc phần cứng, ngôn ngữ, cấp phát đối tượng, bộ nhớ đệm, I/O và bản chất phép toán. Nhưng so sánh **số bước tăng theo kích thước tối đa** giúp sớm loại phương án không khả thi.

| Kích thước giả định | `O(n)` | `O(n log₂n)` (ước lượng) | `O(n²)` |
|---|---:|---:|---:|
| `n = 2_000` | 2.000 | khoảng 21.932 | 4.000.000 |
| `n = 200_000` | 200.000 | khoảng 3.521.928 | 40.000.000.000 |

Các con số chỉ minh họa **tốc độ tăng**, không phải số phép toán máy, thời gian chạy hay cam kết đạt giới hạn.

Quy trình đánh giá:

1. Ghi rõ tham số và các giới hạn lớn nhất, kể cả tổng qua nhiều test.
2. Tính độ phức tạp **xấu nhất** của từng phương án; phân biệt kỳ vọng, trung bình và khấu hao (amortized) nếu cấu trúc dữ liệu có các loại bảo đảm khác nhau.
3. Ước lượng thao tác thực tế: quét mảng, sắp xếp, truy cập `HashMap`, sao chép chuỗi, cấp phát nhiều đối tượng có chi phí khác nhau.
4. Cộng chi phí tiền xử lý, mỗi truy vấn và xuất dữ liệu. Với `Q` truy vấn, ví dụ `O(n log n + Q log n)` có thể hợp lý hơn `O(nQ)` dù tiền xử lý tốn thêm.
5. Thử trường hợp gần giới hạn trong đúng môi trường triển khai nếu giới hạn thực thi chặt.

Với vòng lặp kép, đừng chỉ nhìn thấy “hai vòng” và kết luận `O(n²)`: hai vòng lồng nhau có thể cùng tăng con trỏ, mỗi phần tử chỉ được đi qua hữu hạn lần, dẫn tới `O(n)`. Ngược lại, lặp qua tất cả cặp `(i,j)` thực sự tốn `Θ(n²)`.

Khi áp dụng tìm kiếm nhị phân trên khoảng giá trị, số lần lặp thường tỷ lệ với `log₂(R)` cho khoảng có `R` giá trị phân biệt, chứ không nhất thiết theo số phần tử `n`. Điều kiện tiên quyết là mệnh đề kiểm tra có tính đơn điệu và phép tính điểm giữa không tràn.

## 6. Kiểm tra bộ nhớ, ngăn xếp và I/O

Độ phức tạp không gian `O(n)` chưa cho biết chính xác byte, nhưng có thể ước lượng ban đầu:

- `int[n]` chứa khoảng `4n` byte **dữ liệu phần tử**, `long[n]` khoảng `8n` byte; còn header, căn chỉnh và các đối tượng liên quan tùy JVM.
- `int[200_000]` có khoảng 800.000 byte dữ liệu (xấp xỉ 0,76 MiB), chưa gồm header. Một mảng `int[200_000][200_000]` cần riêng dữ liệu phần tử khoảng **160 GB** theo đơn vị thập phân; chưa kể rất nhiều mảng con. Không thể chọn biểu diễn này trong phần lớn giới hạn bộ nhớ thông thường.
- `ArrayList<Integer>` và `HashMap<Integer, Integer>` thường tiêu thụ nhiều bộ nhớ hơn mảng primitive tương đương do tham chiếu, boxing và cấu trúc bảng; không suy ra byte chính xác từ ký hiệu `O(n)`.
- Đồ thị vô hướng có `E` cạnh thường lưu **hai lượt kề**. Kích thước bộ nhớ của biểu diễn danh sách kề vẫn tỷ lệ `O(V+E)`, nhưng hệ số và kiểu lưu trữ rất quan trọng.
- Đệ quy sâu `O(n)` có thể gây `StackOverflowError` dù heap còn đủ; với đường đi dài hoặc đồ thị dạng dây, cân nhắc DFS/BFS lặp bằng ngăn xếp/hàng đợi tường minh.
- Đầu vào nhiều số/chuỗi nên đọc bằng bộ đệm; tránh đọc toàn bộ tệp vào một chuỗi nếu kích thước tệp có thể lớn. Đầu ra khổng lồ cũng có chi phí tối thiểu tỷ lệ với lượng dữ liệu phải in.

Cần phân biệt **bộ nhớ phụ (auxiliary space)** và bộ nhớ tổng: thuật toán xử lý từng phần tử ngay khi đọc có thể dùng `O(1)` bộ nhớ phụ, nhưng nếu yêu cầu giữ và trả về toàn bộ mảng đầu vào thì chi phí lưu trữ đầu vào/đầu ra vẫn tồn tại.

## 7. Miền giá trị có thể thay đổi hẳn thuật toán

| Điều kiện trong đặc tả | Hệ quả khi thiết kế |
|---|---|
| `n` nhỏ, ví dụ vài nghìn | Duyệt cặp `O(n²)` có thể đáng xem xét nếu tính toán mỗi cặp rẻ và giới hạn cho phép |
| `n` đến hàng trăm nghìn | Nghiêng về `O(n)` hoặc `O(n log n)`; phải chứng minh nếu dùng vòng lặp bậc hai |
| Giá trị nguyên thuộc miền nhỏ `0..U` | Có thể dùng mảng đếm/đánh dấu kích thước `U+1`; phải kiểm tra `U` và bộ nhớ |
| Giá trị thuộc miền rất rộng | Không cấp phát mảng theo `max − min + 1` khi khoảng lớn; cân nhắc sắp xếp, băm hoặc nén tọa độ |
| Dữ liệu đã sắp xếp | Tìm kiếm nhị phân/hai con trỏ có thể phù hợp; cần giữ bất biến thứ tự |
| Số âm được phép xuất hiện | Nhiều lập luận cửa sổ trượt dựa trên tổng tăng dần sẽ không còn áp dụng |
| Cạnh đồ thị có trọng số âm | Không mặc định dùng Dijkstra; thuật toán đường đi phải phù hợp với miền trọng số và chu trình âm |
| `E` nhỏ so với `V²` | Danh sách kề thường phù hợp hơn ma trận `V×V` |
| Có rất nhiều truy vấn trên dữ liệu ít đổi | Cân nhắc tiền xử lý hoặc cấu trúc dữ liệu để giảm chi phí mỗi truy vấn |

Một quyết định thuật toán có thể đồng thời phụ thuộc vào **miền dữ liệu, số thao tác và tài nguyên**. Ví dụ, bảng đếm có thời gian tốt khi miền khóa nhỏ nhưng bộ nhớ `O(U)` sẽ bất khả thi khi `U` cực lớn dù `n` nhỏ.

## 8. Ví dụ hoàn chỉnh: tổng lớn nhất của dãy con liên tiếp

**Đặc tả**

- Đầu vào: số nguyên `n` với `1 ≤ n ≤ 200_000`; tiếp theo là `n` số nguyên `a[i]` với `−10^9 ≤ a[i] ≤ 10^9`, có thể âm, dương hoặc bằng 0.
- Đầu ra: tổng lớn nhất của **một dãy con liên tiếp không rỗng**. Không được chọn dãy rỗng có tổng 0.
- Thứ tự phần tử phải giữ nguyên; không giả định dãy được sắp xếp.
- Giả sử một bộ dữ liệu đầu vào và đầu vào tuân thủ các giới hạn trên.

**Suy luận từ ràng buộc**

- Duyệt mọi dãy con và tính tổng lại từ đầu có thể tốn `O(n³)`; duyệt mọi cặp biên bằng tổng tiền tố tốn `O(n²)`. Với `n = 200_000`, `n² = 4 × 10^10` là lý do để tìm cách tuyến tính.
- Tổng trị tuyệt đối của nhiều nhất `200_000` phần tử không vượt `2 × 10^14`, nên dùng `long` cho tổng; `int` không đủ.
- Có thể xử lý từng phần tử khi đọc, không cần giữ cả mảng, dùng `O(1)` bộ nhớ phụ.

**Bất biến của thuật toán Kadane**

Sau khi xử lý `a[i]`, gọi `ending` là tổng lớn nhất của dãy con liên tiếp **không rỗng và kết thúc đúng tại `i`**. Một dãy như thế hoặc chỉ gồm `a[i]`, hoặc nối `a[i]` vào dãy tốt nhất kết thúc tại `i−1`:

`ending = max(a[i], ending_trước + a[i])`.

Biến `best` lưu giá trị lớn nhất trong các `ending` đã xét. Bất biến này được duy trì ở mỗi bước, nên khi duyệt hết mảng `best` chính là kết quả cần tìm. Khởi tạo `best = Long.MIN_VALUE` giúp xử lý đúng dãy toàn số âm.

**Mã Java 17+ hoàn chỉnh**

Lưu chương trình dưới tên `MaxSubarray.java`:

~~~java
import java.io.BufferedInputStream;
import java.io.EOFException;
import java.io.IOException;

public class MaxSubarray {
    private static final class FastInput {
        private final BufferedInputStream input =
                new BufferedInputStream(System.in);
        private final byte[] buffer = new byte[1 << 16];
        private int position = 0;
        private int length = 0;

        private int readByte() throws IOException {
            if (position >= length) {
                length = input.read(buffer);
                position = 0;
                if (length < 0) return -1;
            }
            return buffer[position++];
        }

        long nextLong() throws IOException {
            int ch;
            do {
                ch = readByte();
            } while (ch >= 0 && ch <= 32);

            if (ch == -1) throw new EOFException("Thieu du lieu");
            int sign = 1;
            if (ch == '-') {
                sign = -1;
                ch = readByte();
            }
            if (ch < '0' || ch > '9') {
                throw new NumberFormatException("So nguyen khong hop le");
            }

            long value = 0;
            while (ch >= '0' && ch <= '9') {
                value = value * 10 + (ch - '0');
                ch = readByte();
            }
            return sign * value;
        }
    }

    public static void main(String[] args) throws Exception {
        FastInput input = new FastInput();
        long rawN = input.nextLong();
        if (rawN < 1 || rawN > 200_000) {
            throw new IllegalArgumentException("n ngoai mien");
        }
        int n = (int) rawN;

        long best = Long.MIN_VALUE;
        long ending = 0;
        for (int i = 0; i < n; i++) {
            long x = input.nextLong();
            if (x < -1_000_000_000L || x > 1_000_000_000L) {
                throw new IllegalArgumentException("a[i] ngoai mien");
            }
            ending = Math.max(x, ending + x);
            best = Math.max(best, ending);
        }
        System.out.println(best);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MaxSubarray.java
java MaxSubarray
~~~

Ví dụ nhập:

~~~text
8
-2 1 -3 4 -1 2 1 -5
~~~

Kết quả xuất chuẩn:

~~~text
6
~~~

Dãy con đạt tổng 6 là `4, −1, 2, 1`. Nếu nhập `3` rồi `-4 -2 -7`, kết quả là `-2`, **không phải 0**, vì yêu cầu dãy con không rỗng.

Mỗi phần tử được xử lý một lần, mỗi lượt dùng số thao tác hằng số: **thời gian `O(n)`, bộ nhớ phụ `O(1)` theo `n`** (bộ đệm đầu vào có kích thước cố định). Cận `|sum| ≤ 2 × 10^14` đảm bảo mọi tổng trung gian thuộc miền `long`. Phần kiểm tra giới hạn đầu vào giúp thể hiện rõ hợp đồng; trong môi trường cam kết dữ liệu hợp lệ, có thể bỏ phần kiểm tra đó.

## 9. Kiểm thử theo biên, không chỉ theo ví dụ thông thường

Khi đặc tả có các miền giá trị và kích thước rõ ràng, bộ kiểm thử nên đi theo chúng:

| Tình huống | Dữ liệu gợi ý | Điều cần kiểm tra |
|---|---|---|
| Kích thước nhỏ nhất | `n=1, a=[−7]` | Trả `−7`; không chọn dãy rỗng |
| Toàn số âm | `[−4,−2,−7]` | Trả `−2` |
| Toàn số dương | `[1,2,3]` | Trả `6` |
| Có số 0 | `[0,−3,0]` | Trả `0` |
| Tổng lớn hơn `int` | `[10^9,10^9,10^9]` | Trả `3_000_000_000` bằng `long` |
| Kích thước tối đa | `200_000` phần tử cùng bằng `10^9` | Trả `200_000_000_000_000`; kiểm tra thời gian và bộ nhớ |
| Đổi dấu nhiều lần | `[−2,1,−3,4,−1,2,1,−5]` | Trả `6`; kiểm tra bất biến cập nhật |

Với một thuật toán khác, lập bộ kiểm thử từ chính miền của bài đó: mảng rỗng nếu hợp lệ; trùng lặp; giá trị min/max; đồ thị không liên thông; chu trình; nhiều truy vấn; tổng kích thước của tất cả test; dữ liệu gây trường hợp xấu nhất của thuật toán hoặc cấu trúc dữ liệu. Có thể đối chiếu ngẫu nhiên đầu vào nhỏ với lời giải chậm nhưng dễ chứng minh để tìm phản ví dụ.

## 10. Những lỗi thường gặp và cách tránh

1. **Chọn kiểu theo từng phần tử, quên biểu thức tổng:** trước khi viết code, lập cận cho tổng, tích, hiệu và số lượng tổ hợp; ép sang `long` **trước** phép toán cần thiết.
2. **Dựa vào số liệu ví dụ thay vì cận lớn nhất:** phân tích `n_max`, `E_max`, `Σn_i` và số truy vấn tối đa; ví dụ nhỏ không đại diện cho bài toán.
3. **Áp dụng một mẹo khi tiền đề không đúng:** hai con trỏ, cửa sổ trượt, Dijkstra, bảng đếm, tìm kiếm nhị phân đều có điều kiện về thứ tự, dấu, miền, trọng số hoặc tính đơn điệu.
4. **Chỉ xét thời gian, bỏ bộ nhớ và stack:** `O(n)` với nhiều object có thể nặng, `O(n²)` mảng có thể vượt memory, đệ quy sâu có thể tràn ngăn xếp.
5. **Hiểu `O(...)` là thời gian đo được:** độ phức tạp là mô hình tăng trưởng; cần xét hằng số, JDK/JVM, I/O và benchmark gần cận trong môi trường chạy thực tế.
6. **Đặc tả mơ hồ về biên:** viết rõ dấu `≤` hay `<`, có cho phép rỗng/trùng/âm/0 không, giá trị không có đáp án và định dạng chính xác của đầu ra.

**Checklist trước khi chốt lời giải:** Miền đầu vào và quan hệ giữa các biến đã rõ chưa? Có trường hợp rỗng, âm, trùng, cực trị không? Đã định nghĩa tham số đo kích thước và tổng qua nhiều test chưa? Kiểu số có chứa mọi kết quả trung gian không? Độ phức tạp thời gian, bộ nhớ và ngăn xếp có chịu được biên trên không? Các giả thiết mà thuật toán cần có thực sự được đặc tả bảo đảm không? Đã thử các trường hợp ở sát từng cận chưa?

Một thuật toán chỉ được xem là phù hợp khi **đúng trên toàn miền đầu vào hợp lệ** và **khả thi với kích thước/tài nguyên được giao**.