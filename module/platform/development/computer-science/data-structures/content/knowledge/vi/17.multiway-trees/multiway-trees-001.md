# Động cơ gom nhiều khóa và con trỏ trong cùng một nút

Trong cây tìm kiếm nhị phân, mỗi nút thường giữ **một khóa** và tối đa **hai liên kết con**. Muốn tìm một khóa nằm sâu trong cây, thuật toán phải lần lượt đi qua nhiều nút. Khi dữ liệu nằm chủ yếu trên đĩa hoặc trong một hệ thống phân cấp bộ nhớ, mỗi lần chuyển sang nút khác có thể kéo theo việc đọc thêm một vùng dữ liệu tương đối tốn kém.

**Cây nhiều nhánh** (*multiway search tree*) chọn một cách tổ chức khác: **gom nhiều khóa có thứ tự và nhiều con trỏ con vào cùng một nút**. Một lần đọc nút cung cấp đủ thông tin để loại bỏ nhiều khoảng giá trị, rồi chọn một trong nhiều nhánh con. Đây là động cơ quan trọng của họ **B-tree**, **B+ tree** và nhiều chỉ mục lưu trữ theo trang.

Bài học tập trung trả lời ba câu hỏi: tại sao một nút cần nhiều khóa, các con trỏ liên hệ với khoảng khóa như thế nào, và tại sao tổ chức đó có thể giảm chiều cao cây cùng số lần truy cập bộ nhớ ngoài. Ta cũng xem xét đánh đổi giữa số nhánh, dung lượng nút và công tìm kiếm bên trong nút.

## 1. Từ nút nhị phân đến nút nhiều nhánh

Giả sử muốn lưu các khóa số nguyên có thứ tự và hỗ trợ tìm kiếm.

Trong một **cây tìm kiếm nhị phân** (*binary search tree*), một nút có dạng:

```text
            [40]
           /    \
        <40      >40

Mỗi nút có 1 khóa và tối đa 2 con.
```

Khi tìm `35`, ta so sánh với `40` rồi chọn nhánh trái. Ở nút kế tiếp, thuật toán lại đọc một khóa và chọn một trong hai nhánh. Với một cây nhị phân cân bằng gồm `n` khóa, số tầng thường có bậc `O(log_2 n)`.

Một **nút nhiều nhánh** có thể chứa nhiều khóa phân cách:

```text
                  +----------------+
                  | 20 | 40 | 60   |
                  +----------------+
                    /    |    |    \
                 P0     P1   P2     P3

Một nút có 3 khóa và 4 con trỏ con.
```

Các khóa `20, 40, 60` chia miền tìm kiếm thành **bốn khoảng**:

| Kết quả so sánh với các khóa trong nút | Nhánh cần đi |
| --- | --- |
| `x < 20` | `P0` |
| `20 < x < 40` | `P1` |
| `40 < x < 60` | `P2` |
| `x > 60` | `P3` |

Trong cách biểu diễn **B-tree có khóa dữ liệu ngay ở nút trong**, nếu `x` bằng `20`, `40` hoặc `60` thì đã tìm thấy khóa tại nút này; không cần xuống con.

Một lần xử lý nút như vậy chọn được **một trong bốn khoảng** thay vì chỉ trái/phải. Nếu một nút chứa nhiều khóa hơn nữa, nó có thể chọn giữa hàng chục hoặc hàng trăm nhánh.

> **Ý tưởng cốt lõi:** Mỗi nút chứa nhiều khóa phân tách không gian tìm kiếm; các con trỏ con dẫn tới những phần dữ liệu thuộc các khoảng do các khóa đó xác định.

## 2. Bất biến sắp xếp: `k` khóa tạo `k + 1` khoảng

Xét một nút trong có `k` khóa **phân biệt và được sắp tăng dần**:

\[
K_0 < K_1 < \dots < K_{k-1}.
\]

Trong mô hình cây tìm kiếm nhiều nhánh cơ bản, nút có thể có **`k + 1` con trỏ con**:

\[
P_0, P_1, \dots, P_k.
\]

Ý nghĩa các nhánh:

- `P_0` chứa các khóa **nhỏ hơn** `K_0`.
- Với `1 \le i < k`, `P_i` chứa các khóa **lớn hơn `K_{i-1}` và nhỏ hơn `K_i`**.
- `P_k` chứa các khóa **lớn hơn** `K_{k-1}`.

Các khoảng trên giả định không có khóa trùng nhau và các khóa phân cách thuộc nút theo mô hình B-tree được minh họa. Nếu dữ liệu cho phép khóa trùng, phải có **quy tắc nhất quán về khóa bằng nhau** hoặc lưu danh sách giá trị tương ứng; không thể tự ý đẩy giá trị bằng khóa phân cách sang một nhánh bất kỳ.

Ví dụ đầy đủ:

```text
                         [20 | 40 | 60]
                       /      |     |      \
                      /       |     |       \
                 [5, 10] [25, 30] [45, 50] [70, 80]

P0: (< 20)       P1: (20, 40)    P2: (40, 60)   P3: (> 60)
```

Tìm `50`:

1. Đọc nút gốc chứa `20, 40, 60`.
2. Xác định `40 < 50 < 60`, nên chỉ đi theo con trỏ `P2`.
3. Đọc nút con chứa `45, 50` và tìm thấy `50`.

Tìm `35`:

1. Tại gốc, xác định `20 < 35 < 40`; chọn `P1`.
2. Nút con chứa `25, 30`. Không có `35`, và đây là lá; kết luận không tìm thấy.

Ta **không phải đọc tất cả bốn nút con** để kiểm tra một khóa. Các khóa phân cách và con trỏ con giúp mỗi bước **loại bỏ những nhánh không thể chứa đáp án**.

### Nút lá khác nút trong

Trong mô hình trên, một **nút trong** giữ khóa cùng các con trỏ con; một **nút lá** giữ những khóa cuối cùng của một đường tìm kiếm và không có con trỏ xuống tầng thấp hơn. Vì thế, quy tắc “`k` khóa đi cùng `k + 1` con trỏ con” mô tả **nút trong đủ nhánh**, không có nghĩa mọi nút lá cũng phải mang những con trỏ không dùng tới.

Với **B+ tree**, khóa ở nút trong thường đóng vai trò *khóa phân cách* để định tuyến; bản ghi hoặc vị trí bản ghi nằm ở lá. Vì vậy, khi tìm thấy giá trị bằng một khóa phân cách của nút trong B+ tree, thuật toán vẫn thường đi xuống nhánh thích hợp để tìm bản ghi ở lá. Cần dùng đúng quy ước so sánh của cấu trúc cụ thể.

## 3. Động cơ lớn nhất: giảm số tầng cần đi qua

Gọi `f` là **hệ số phân nhánh** (*fan-out*): số con trỏ con mà một nút trong có thể sử dụng. Trong cây nhị phân, `f \le 2`; cây nhiều nhánh có thể có `f` lớn hơn nhiều.

Một cây có `f` nhánh ở mỗi nút, giả sử các nhánh được sử dụng khá đồng đều, có số vị trí tiềm năng tăng theo các mức:

```text
                 Mức 0 (gốc):            1 nút
                 Mức 1:                  f nút
                 Mức 2:                  f^2 nút
                 Mức 3:                  f^3 nút
                 ...
```

Khi cây được cân bằng và mỗi nút trong có đủ nhiều con theo bất biến của cấu trúc, độ cao có thể được khống chế ở bậc:

\[
h = O(\log_f n),
\]

với `n` là quy mô dữ liệu theo mô hình đang xét. Dùng định luật đổi cơ số:

\[
\log_f n=\frac{\log_2 n}{\log_2 f}.
\]

Nếu tăng `f` từ `2` lên `100`, một đường đi có thể ngắn hơn đáng kể, vì mỗi mức định tuyến giữa nhiều khoảng hơn.

Ví dụ minh họa với khoảng **một triệu** phần tử và mức lấp đầy phù hợp:

| Hệ số phân nhánh giả định | `log_f(1.000.000)` xấp xỉ | Ý nghĩa |
| ---: | ---: | --- |
| 2 | 19,93 | Cần khoảng 20 mức quyết định nhị phân |
| 10 | 6 | Khoảng 6 mức |
| 100 | 3 | Khoảng 3 mức |
| 200 | 2,62 | Khoảng 3 mức |

Những con số là **so sánh lý tưởng theo hệ số phân nhánh**, không phải số tầng chính xác của mọi cây một triệu bản ghi. Chiều cao thực tế phụ thuộc cách khóa nằm trong nút, mức đầy của trang, số khóa được chứa ở lá, quy tắc cân bằng và độ lớn bản ghi.

Điểm quan trọng là: nếu mỗi lần đi xuống một nút mới phải đọc thêm một trang dữ liệu tốn kém, **giảm vài tầng có thể tạo ra lợi ích đáng kể hơn việc tiết kiệm vài phép so sánh khóa**.

## 4. Vì sao gom khóa và con trỏ phù hợp với trang đĩa?

Trên thiết bị lưu trữ, cơ sở dữ liệu thường tổ chức dữ liệu thành các **trang** (*pages*), chẳng hạn 4 KiB, 8 KiB hoặc kích thước khác tùy hệ thống. Thay vì đọc từng khóa rời rạc, hệ thống đọc một trang vào bộ nhớ. Một nút B-tree/B+ tree thường được thiết kế để nằm trong một trang hoặc đơn vị lưu trữ tương ứng.

```text
                  Một trang lưu trữ
          +--------------------------------+
          | Thông tin nút / header         |
          +--------------------------------+
          | K0 | K1 | K2 | ... | Kk-1      |
          +--------------------------------+
          | P0 | P1 | P2 | ... | Pk        |
          +--------------------------------+

Một lần nạp trang có thể lấy cả các khóa phân cách
và các địa chỉ trang con cần cho quyết định tiếp theo.
```

Ở đây `P_i` không nhất thiết là con trỏ máy `T*`; trong cấu trúc trên đĩa, nó có thể là **mã trang**, **địa chỉ khối** hoặc một định danh được hệ thống lưu trữ dùng để tải trang con.

Nếu một nút chỉ chứa một khóa và hai con trỏ, phần lớn một trang có thể không được tận dụng cho thông tin định tuyến. Nếu đặt nhiều cặp khóa–con trỏ trong cùng trang:

1. Một lần đọc trang cung cấp nhiều khóa để phân biệt các khoảng.
2. Số nhánh trên mỗi nút lớn hơn, giúp giảm chiều cao cây.
3. Số trang cần truy cập trên một đường tìm kiếm thường nhỏ hơn, nhất là khi các tầng chưa có trong bộ nhớ đệm.
4. Các khóa trong cùng nút có tính cục bộ cao hơn so với nhiều nút được cấp phát rải rác.

**Lưu ý:** Không phải mỗi lần truy cập nút đều tạo ra một lần đọc đĩa. Nếu trang đã nằm trong bộ nhớ đệm, thao tác có thể hoàn toàn diễn ra trong RAM. Mô hình chi phí truy cập trang là một cách phân tích hữu ích khi đánh giá cấu trúc dữ liệu cho bộ nhớ ngoài, không phải con số I/O cố định cho mọi lần tìm kiếm.

## 5. Một ví dụ tính sức chứa của nút

Giả sử ta thiết kế một nút trong đơn giản có những thông số **minh họa** sau:

- Kích thước trang: **4.096 byte**.
- Header và metadata khác: **128 byte**.
- Mỗi khóa: **16 byte**.
- Mỗi con trỏ trang con: **8 byte**.
- Một nút trong có `k` khóa và `k + 1` con trỏ.

Tổng số byte ước tính:

\[
B(k)=128+16k+8(k+1)=136+24k.
\]

Để nút nằm gọn trong trang:

\[
136+24k\le4096
\quad\Rightarrow\quad
k\le165.
\]

Như vậy trong mô hình đơn giản này, một nút trong có thể chứa tối đa **165 khóa và 166 con trỏ con**. Một lần đọc trang chứa đủ các khóa định tuyến cho tối đa 166 nhánh.

| Thành phần khi `k = 165` | Số byte |
| --- | ---: |
| Header | 128 |
| 165 khóa × 16 byte | 2.640 |
| 166 con trỏ × 8 byte | 1.328 |
| **Tổng** | **4.096** |

Đây **không** phải giới hạn chung của B-tree hoặc B+ tree. Một trang thật còn có thể cần thông tin quản lý slot, khóa dài thay đổi, nén khóa, phiên bản bản ghi, cờ trạng thái, căn chỉnh và các vùng dự trữ; vì vậy fan-out thực tế có thể khác đáng kể. Nút lá cũng thường có bố cục khác nút trong, vì nó phải lưu hoặc dẫn đến dữ liệu bản ghi.

### Vì sao không tăng fan-out vô hạn?

Gom càng nhiều khóa vào một nút có thể giảm số tầng, nhưng cũng tạo đánh đổi:

| Lợi ích của nút lớn | Chi phí hoặc giới hạn |
| --- | --- |
| Nhiều nhánh hơn, cây thấp hơn | Cần nhiều byte cho khóa và con trỏ |
| Ít lần chuyển trang khi tìm | Tìm vị trí bên trong nút có thể tốn nhiều so sánh hơn |
| Tận dụng tốt một lần đọc trang | Trang lớn có thể tăng chi phí truyền dữ liệu hoặc lãng phí khi truy cập ít nội dung |
| Ít nút hơn trong nhiều trường hợp | Chèn/xóa có thể phải dịch khóa, tách/gộp nút và cập nhật con trỏ |
| Các khóa trong nút tương đối gần nhau | Phải cân nhắc cache CPU, kích thước khóa và bố cục bộ nhớ |

Vì thế mục tiêu không phải “một nút càng lớn càng tốt”, mà là **chọn số khóa và con trỏ phù hợp đơn vị truyền dữ liệu cùng kiểu truy cập chủ yếu**.

## 6. Tìm kiếm bên trong nút có nhiều khóa

Khi đã tải một nút chứa `k` khóa được sắp xếp, thuật toán cần xác định khóa đang tìm nằm trong khoảng nào. Có hai cách phổ biến:

| Cách xử lý một nút | Số phép so sánh trong nút | Đặc điểm |
| --- | --- | --- |
| Quét tuyến tính | O(k) | Dễ cài đặt, có thể hợp lý khi nút rất nhỏ |
| Tìm nhị phân trong mảng khóa của nút | O(log k) | Phù hợp khi số khóa lớn và được sắp thứ tự |

Nếu có `h` tầng, mỗi tầng cần tìm trong một nút có tối đa `k` khóa, mô hình đơn giản cho:

\[
\text{CPU comparisons}=O(h\log k)
\]

khi tìm nhị phân bên trong mỗi nút. Với cây cân bằng có `h=O(\log_f n)` và `f` cùng bậc với `k`, số phép so sánh tổng thể vẫn có bậc **O(log n)**.

Trong khi đó, nếu mỗi nút nằm trong một trang và chỉ cần đọc **một nút trên mỗi mức**, số lần truy cập trang dọc một đường tìm kiếm tỷ lệ với `h`, tức khoảng **O(log_f n)** trong mô hình bộ nhớ ngoài thích hợp.

Đó là **sự phân biệt quan trọng**:

- Trong RAM, gom nhiều khóa không tự động khiến tổng số phép so sánh thấp hơn theo bậc Big-O; còn phải xét chi phí tìm trong nút.
- Trên đĩa hoặc hệ thống phân trang, nó có thể giảm mạnh **số lần phải chuyển sang trang khác**, vốn thường đắt hơn nhiều phép so sánh khóa nội bộ.

## 7. Mã Java minh họa quyết định nhánh

Đoạn mã dưới đây cài đặt **tìm kiếm** trên một cây nhiều nhánh nhỏ theo mô hình B-tree có khóa dữ liệu tại cả nút trong và nút lá. Mục đích là cho thấy mối quan hệ giữa **mảng khóa đã sắp** và **mảng con trỏ con**; đây **chưa phải cài đặt B-tree hoàn chỉnh** với các thuật toán chèn, tách nút, xóa hoặc cân bằng.

```java
import java.util.Arrays;

public class MultiwayNodeSearch {
    static final class Node {
        final int[] keys;
        final Node[] children; // null nghia la nut la

        Node(int[] keys, Node[] children) {
            this.keys = keys.clone();
            this.children = children == null ? null : children.clone();

            for (int i = 1; i < this.keys.length; i++) {
                if (this.keys[i - 1] >= this.keys[i]) {
                    throw new IllegalArgumentException("Keys not increasing");
                }
            }

            if (this.children != null
                    && this.children.length != this.keys.length + 1) {
                throw new IllegalArgumentException(
                    "Internal node needs k + 1 children"
                );
            }
        }

        boolean isLeaf() {
            return children == null;
        }
    }

    static boolean contains(Node root, int target) {
        Node current = root;

        while (current != null) {
            // lower_bound: vi tri dau tien co key >= target.
            int lo = 0;
            int hi = current.keys.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (current.keys[mid] < target) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }

            if (lo < current.keys.length
                    && current.keys[lo] == target) {
                return true; // B-tree: khoa co the nam o nut trong
            }

            if (current.isLeaf()) {
                return false;
            }

            // lo cung la chi so nhanh con can di theo.
            current = current.children[lo];
        }

        return false;
    }

    public static void main(String[] args) {
        Node p0 = new Node(new int[] {5, 10}, null);
        Node p1 = new Node(new int[] {25, 30}, null);
        Node p2 = new Node(new int[] {45, 50}, null);
        Node p3 = new Node(new int[] {70, 80}, null);

        Node root = new Node(
            new int[] {20, 40, 60},
            new Node[] {p0, p1, p2, p3}
        );

        for (int x : new int[] {10, 20, 35, 50, 60, 80}) {
            System.out.println(x + ": " + contains(root, x));
        }
    }
}
```

Kết quả:

```text
10: true
20: true
35: false
50: true
60: true
80: true
```

Khi tìm `50`, tìm nhị phân trên các khóa gốc `[20, 40, 60]` cho vị trí đầu tiên có khóa lớn hơn hoặc bằng `50` là `2` (khóa `60`). Vì `50` không bằng `60`, thuật toán đi theo `children[2]`, tức nút lá `[45, 50]`. Ở đó, khóa `50` được tìm thấy.

**Giới hạn mô phỏng:** Constructor chỉ kiểm tra thứ tự khóa trong từng nút và số lượng con trỏ, **không tự xác minh tất cả khóa ở các cây con thuộc đúng khoảng**, cũng không áp dụng mức lấp đầy tối thiểu hay điều kiện các lá có cùng độ sâu. Những bất biến đó phải được đảm bảo bởi thuật toán xây dựng/chỉnh sửa một B-tree thực sự.

## 8. Động cơ gom khóa dẫn tới B-tree và B+ tree

Cây tìm kiếm nhiều nhánh chỉ nêu ý tưởng nút giữ nhiều khóa và nhiều liên kết. Khi cần bảo đảm cấu trúc không thoái hóa thành một đường dài sau nhiều lần thêm/xóa, ta cần thêm **bất biến cân bằng**.

### B-tree: nút nhiều khóa, lá cùng độ sâu

Một quy ước phổ biến là định nghĩa **cấp `m`** (*order*) của B-tree bằng **số con tối đa của một nút trong**:

- Nút trong có nhiều nhất `m` con và nhiều nhất `m - 1` khóa.
- Ngoại trừ gốc, nút trong có ít nhất `ceil(m/2)` con và `ceil(m/2) - 1` khóa.
- Tất cả lá nằm ở cùng độ sâu.
- Khi nút đầy, chèn có thể dẫn tới **tách nút** và đẩy khóa phân cách lên nút cha.
- Khi xóa gây thiếu khóa, cây có thể mượn khóa hoặc gộp nút để phục hồi bất biến.

Một số tài liệu dùng từ **order** hoặc **degree** với định nghĩa khác, ví dụ **bậc tối thiểu `t`** với giới hạn tối đa `2t - 1` khóa. Vì vậy, khi đọc công thức, phải xác nhận cách tài liệu định nghĩa cấp/bậc trước khi so sánh số khóa tối thiểu và tối đa.

### B+ tree: tách định tuyến khỏi dữ liệu ở lá

Trong B+ tree:

- Nút trong chứa các **khóa phân cách và liên kết đến trang con** để định tuyến.
- Lá chứa **khóa và dữ liệu bản ghi hoặc con trỏ đến bản ghi** theo thiết kế cụ thể.
- Các lá thường có liên kết sang lá kế tiếp, hỗ trợ duyệt theo thứ tự và truy vấn phạm vi.
- Khóa phân cách ở nút trong **có thể lặp lại** giá trị khóa ở lá; không nên áp dụng máy móc quy tắc “bằng khóa ở nút trong thì trả về bản ghi” của ví dụ B-tree.

Việc các nút trong chủ yếu làm công việc định tuyến có thể giúp một trang chứa nhiều khóa–con trỏ hơn so với việc phải mang bản ghi lớn trong mỗi nút. Điều đó tăng fan-out hữu ích và thường rất hợp với các chỉ mục cơ sở dữ liệu.

| Khía cạnh | B-tree (mô hình thông dụng) | B+ tree (mô hình thông dụng) |
| --- | --- | --- |
| Nút trong | Có thể chứa khóa cùng dữ liệu liên quan | Chủ yếu chứa khóa phân cách và con trỏ con |
| Nút lá | Có khóa/dữ liệu | Chứa các khóa gắn với dữ liệu hoặc vị trí bản ghi |
| Tìm thấy khóa tại nút trong | Có thể kết thúc tìm kiếm khóa | Thường cần xuống lá để lấy bản ghi |
| Duyệt khoảng liên tiếp | Có thể duyệt theo thứ tự qua cây | Thường thuận tiện nhờ các lá được liên kết |
| Động cơ tổ chức nút | Gom nhiều khóa và nhiều nhánh, duy trì cân bằng | Tương tự, tối ưu định tuyến trang và truy vấn phạm vi |

Các chi tiết chính xác phụ thuộc biến thể và cài đặt; điểm chung của cả hai là **một nút giữ nhiều thông tin định tuyến, nhờ đó cây có thể rộng và thấp**.

## 9. Khi nào lợi ích của nút nhiều khóa rõ rệt?

| Hoàn cảnh | Lý do nên cân nhắc cấu trúc nhiều nhánh |
| --- | --- |
| Chỉ mục cơ sở dữ liệu có hàng triệu khóa | Giảm số trang cần truy cập trên một đường tìm kiếm |
| Kho khóa nằm trên SSD, HDD hoặc hệ thống lưu trữ phân trang | Tận dụng mỗi lần đọc trang để lấy nhiều khóa và liên kết |
| Cần tìm kiếm chính xác và truy vấn khoảng | Nút sắp khóa giúp định tuyến; B+ tree hỗ trợ duyệt lá liên tiếp |
| Cần thêm/xóa nhiều mà vẫn kiểm soát độ cao | Các biến thể cây cân bằng áp đặt mức lấp đầy và cùng độ sâu của lá |
| Số khóa lớn nhưng từng khóa ngắn, kích thước trang khá lớn | Một trang có thể chứa nhiều khóa và con trỏ, tạo fan-out cao |

Ngược lại, trong một bài toán nhỏ hoàn toàn nằm trong RAM, một mảng đã sắp xếp, bảng băm hoặc cây nhị phân cân bằng có thể phù hợp hơn tùy loại thao tác. **Cây nhiều nhánh không mặc nhiên là lựa chọn nhanh nhất cho mọi dữ liệu**. Cần cân nhắc số lần truy cập trang, chi phí so sánh trong nút, cập nhật cấu trúc, mức sử dụng bộ nhớ và yêu cầu duyệt có thứ tự.

## 10. Lỗi suy luận thường gặp

1. **“Nút nhiều nhánh chỉ có nhiều con trỏ hơn, không cần nhiều khóa.”** Các khóa phân cách là thông tin quyết định nên đi theo nhánh nào. Không có quy tắc định tuyến, thêm con trỏ không tự tạo ra cây tìm kiếm hiệu quả.
2. **“Có ba khóa thì chỉ cần ba con trỏ con.”** Trong mô hình nút trong với `k` khóa phân cách phân biệt, thường cần `k + 1` khoảng và `k + 1` con trỏ.
3. **“Tất cả các khóa ở mọi nút đều được lưu không cần thứ tự.”** Tìm kiếm theo khoảng cần các khóa trong nút được sắp và các cây con tuân theo đúng ranh giới.
4. **“Fan-out lớn làm mọi phép tìm kiếm thành O(1).”** Vẫn cần đi qua các tầng và tìm trong nút. Cấu trúc cân bằng thường có chiều cao O(log_f n), không phải hằng số tuyệt đối cho mọi quy mô.
5. **“Số tầng nhỏ hơn đồng nghĩa số phép so sánh luôn ít hơn.”** Nút chứa nhiều khóa cần nhiều so sánh nội bộ; lợi ích lớn nhất có thể là giảm số lần chuyển trang.
6. **“Một con trỏ con trong cây trên đĩa luôn là địa chỉ RAM.”** Nó có thể là mã trang hoặc địa chỉ khối được hệ thống lưu trữ dùng để lấy nút con.
7. **“Nếu khóa bằng khóa phân cách ở nút trong, B+ tree chắc chắn có thể trả về bản ghi tại chỗ.”** Nút trong B+ tree chủ yếu phục vụ định tuyến; thường phải xuống lá để lấy dữ liệu.
8. **“B-tree có thể thêm vô hạn khóa vào một nút.”** Kích thước trang và các giới hạn khóa/con trỏ buộc nút có sức chứa hữu hạn; khi đầy phải tách hoặc tái tổ chức.
9. **“Mọi B-tree đều có cùng định nghĩa `m`.”** Tài liệu khác nhau có thể định nghĩa order, degree hoặc minimum degree khác nhau; phải kiểm tra quy ước trước khi áp công thức.
10. **“Bộ đệm đã cache toàn bộ thì mô hình I/O vẫn quyết định tuyệt đối tốc độ.”** Trong RAM, so sánh nội bộ, bố cục dữ liệu và cache CPU có thể quan trọng hơn số lần đọc trang từ thiết bị.

## 11. Tự kiểm tra

**Câu 1.** Một nút trong chứa bốn khóa phân biệt được sắp tăng dần. Theo mô hình cây tìm kiếm nhiều nhánh cơ bản, có bao nhiêu khoảng tìm kiếm và tối đa bao nhiêu con trỏ con tương ứng?

**Đáp án:** Có năm khoảng và tối đa năm con trỏ con theo các khoảng đó: trước khóa nhỏ nhất, ba khoảng giữa bốn khóa và sau khóa lớn nhất.

**Câu 2.** Nút chứa các khóa `[10, 25, 50]`. Nếu khóa đang tìm là `40` và các con trỏ được đánh số `P0` đến `P3` từ trái sang phải, phải chọn nhánh nào?

**Đáp án:** `P2`, vì `25 < 40 < 50`.

**Câu 3.** Tại sao gom nhiều khóa và con trỏ trong một trang thường hữu ích hơn cho cơ sở dữ liệu trên đĩa so với mô hình một khóa mỗi nút?

**Đáp án:** Một lần nạp trang có thể chứa nhiều khóa phân cách và nhiều địa chỉ trang con. Fan-out lớn làm giảm chiều cao và thường giảm số trang phải truy cập trên đường tìm kiếm.

**Câu 4.** Nếu nút có `k` khóa và `k + 1` con trỏ, mỗi khóa chiếm 16 byte, mỗi con trỏ 8 byte, header 128 byte, tổng byte được tính thế nào?

**Đáp án:** `128 + 16k + 8(k + 1) = 136 + 24k` byte.

**Câu 5.** Với trang 4.096 byte và mô hình ở Câu 4, số khóa nguyên lớn nhất vừa trang là bao nhiêu?

**Đáp án:** `k = 165`, vì `136 + 24 × 165 = 4.096`. Nút đó có 166 con trỏ theo mô hình, chưa tính các metadata bổ sung ngoài giả định.

**Câu 6.** Nếu một cây nhiều nhánh cân bằng có fan-out hiệu dụng khoảng 100, tại sao chiều cao có thể nhỏ hơn cây nhị phân cân bằng với cùng quy mô lớn?

**Đáp án:** Mỗi tầng có thể chọn trong khoảng 100 nhánh thay vì 2; số vị trí tăng theo `100^h` thay vì `2^h`. Vì vậy, số tầng cần đi thường gần `log_100 n` thay vì `log_2 n` trong mô hình lý tưởng.

**Câu 7.** Có phải fan-out lớn luôn giảm độ phức tạp CPU tìm kiếm xuống O(1) không?

**Đáp án:** Không. Vẫn cần tìm trong các khóa của từng nút và đi qua nhiều tầng. Với tìm nhị phân trong nút và cây cân bằng, tổng số so sánh thường vẫn O(log n); lợi ích về truy cập trang có thể rõ hơn.

**Câu 8.** Trong mô hình B-tree có khóa dữ liệu ở nút trong, khi khóa tìm kiếm bằng một khóa tại nút trong, thuật toán có thể làm gì? B+ tree có khác không?

**Đáp án:** B-tree có thể kết luận đã tìm thấy khóa ngay tại nút trong. Trong B+ tree, khóa nút trong chủ yếu dùng để định tuyến nên thường cần đi xuống lá để lấy bản ghi tương ứng.

**Câu 9.** Vì sao một nút lá có thể không cần `k + 1` con trỏ xuống nút con, dù nó chứa `k` khóa?

**Đáp án:** Lá không có tầng con để đi xuống. Quy tắc `k + 1` con trỏ áp dụng cho nút trong sử dụng các khóa làm ranh giới giữa những cây con.

**Câu 10.** Nêu hai đánh đổi khi tăng số khóa của mỗi nút.

**Đáp án:** Nút lớn hơn cần nhiều bộ nhớ và có thể tốn thêm so sánh/dịch dữ liệu khi tìm hoặc cập nhật trong nút; bù lại, nó tăng fan-out và có thể giảm số tầng cùng số lần chuyển trang.

**Câu 11.** Đoạn mã Java minh họa ở bài đã đủ để gọi là một B-tree hoàn chỉnh chưa?

**Đáp án:** Chưa. Nó chỉ tìm kiếm trên một cây nhỏ được dựng sẵn; chưa thực hiện chèn, tách/gộp nút, xử lý thiếu khóa hoặc bảo đảm mọi lá cùng độ sâu và mức lấp đầy tối thiểu.

**Câu 12.** Nếu một trang chỉ mục đã có sẵn trong RAM, lần tìm trong trang đó có phải luôn phát sinh một lần đọc đĩa không?

**Đáp án:** Không. Khi trang đã có trong bộ nhớ đệm, có thể tìm trong RAM. Phân tích số lần truy cập trang trên đường tìm kiếm không đồng nghĩa số lần I/O đĩa thực tế ở mọi lần gọi.

**Điểm ghi nhớ:** Gom nhiều khóa có thứ tự và `k + 1` liên kết con trong một nút trong giúp một lần xử lý nút định tuyến tới **một trong nhiều khoảng khóa**. Khi nút được thiết kế phù hợp với trang lưu trữ và cây được giữ cân bằng, fan-out lớn có thể làm cây thấp hơn và giảm số lần đọc trang trên đường tìm kiếm. Đây là động cơ nền tảng của cây nhiều nhánh và họ B-tree/B+ tree.
