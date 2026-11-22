# Tập hợp rời nhau (DSU) và thao tác hợp nhất

**Disjoint Set Union (DSU)**, còn gọi là **Union-Find**, là cấu trúc dữ liệu quản lý các phần tử được chia thành những **nhóm rời nhau**: mỗi phần tử thuộc đúng một nhóm. Hai thao tác cốt lõi là **`find(x)`** để tìm đại diện của nhóm chứa `x` và **`union(a,b)`** để hợp nhất nhóm chứa `a` với nhóm chứa `b`.

Ví dụ, mạng có các máy `0..5`. Ban đầu mỗi máy tạo một thành phần riêng. Thêm kết nối `0–1` rồi `1–2` khiến `0,1,2` cùng một thành phần, dù `0` và `2` không có cạnh nối trực tiếp. Khi cần hỏi liên tục “hai máy có kết nối gián tiếp không?”, DSU ghi nhớ **quan hệ cùng thành phần** đã được hình thành qua các lần hợp nhất.

DSU không phải cấu trúc tìm đường đi: nó không lưu toàn bộ đường đi, khoảng cách, thứ tự duyệt hay cấu trúc cạnh của đồ thị. Hãy chọn DSU khi bài toán chủ yếu **thêm liên kết và hỏi những phần tử nào đã ở cùng nhóm**.

## 1. Mô hình nhóm và hợp đồng thao tác

Với `n` phần tử đánh số `0,1,...,n-1`, DSU biểu diễn một **phân hoạch** của tập đầu vào: các nhóm không rỗng, không giao nhau và hợp của chúng là toàn bộ tập phần tử.

```text
Ban đầu:    {0} {1} {2} {3} {4} {5}
union(0,1): {0,1} {2} {3} {4} {5}
union(1,2): {0,1,2} {3} {4} {5}
union(3,4): {0,1,2} {3,4} {5}
union(2,4): {0,1,2,3,4} {5}
```

Sau chuỗi trên có hai nhóm, và gọi `union(0,3)` thêm lần nữa không thay đổi phân hoạch vì hai phần tử đã cùng nhóm.

| Thao tác | Ý nghĩa | Hợp đồng |
|---|---|---|
| `DSU(n)` | Khởi tạo `n` phần tử | Ban đầu có `n` nhóm đơn lẻ |
| `find(x)` | Tìm đại diện của nhóm chứa `x` | Hai phần tử cùng nhóm có cùng đại diện |
| `union(a,b)` | Hợp nhất hai nhóm | Trả `true` nếu gộp được hai nhóm khác nhau; trả `false` nếu chúng đã cùng nhóm |
| `connected(a,b)` | Kiểm tra cùng nhóm | Tương đương `find(a) == find(b)` |
| `componentSize(x)` | Đếm phần tử trong nhóm chứa `x` | Trả kích thước hiện tại của nhóm |
| `count()` | Đếm số nhóm | Giảm đúng một sau mỗi lần gộp thành công |

**Đại diện** chỉ là tên nhận dạng nhóm để so sánh, không phải phần tử “quan trọng nhất” hay đại diện cố định. Sau một phép hợp nhất, gốc đại diện có thể thay đổi. Không dựa vào giá trị cụ thể mà `find` trả về ngoài tính chất **bằng nhau khi cùng nhóm**.

DSU thường quản lý phần tử bằng chỉ số mảng. Nếu ID gốc là chuỗi hoặc số rất lớn và thưa, hãy ánh xạ chúng sang các chỉ số liên tiếp trước khi dùng mảng.

## 2. Lưu bằng rừng cây và ba bất biến

DSU hiệu quả thường sử dụng hai mảng:

- `parent[x]`: cha của phần tử `x` trong một cây biểu diễn nhóm. `x` là **gốc** nếu `parent[x] == x`.
- `size[r]`: số phần tử thuộc nhóm có gốc hiện tại là `r`. **Chỉ giá trị `size` tại gốc mới đáng tin**; ô `size` của một phần tử không còn là gốc có thể lưu giá trị cũ.

Mỗi nhóm là một cây, tất cả nhóm là một **rừng cây**. Cạnh cha–con trong rừng chỉ phục vụ lưu trữ, không nhất thiết là cạnh thực sự trong đồ thị đầu vào.

```text
parent[0] = 0       0 (gốc nhóm {0,1,2})
parent[1] = 0      / \
parent[2] = 0     1   2

parent[3] = 3       3 (gốc nhóm {3,4})
parent[4] = 3       |
                    4
parent[5] = 5       5 (gốc nhóm {5})
```

Ba bất biến cần giữ sau mọi thao tác:

1. **Mỗi phần tử đi theo quan hệ cha qua hữu hạn bước sẽ đến đúng một gốc**. Không có chu trình cha giữa các nút khác nhau.
2. **Hai phần tử cùng nhóm khi và chỉ khi chúng có cùng gốc**. Đây là bất biến bảo đảm tính đúng của truy vấn `connected`.
3. **Mỗi gốc lưu đúng kích thước nhóm và `components` lưu đúng số nhóm**. Hợp nhất thành công giảm số nhóm một đơn vị; hợp nhất lặp lại giữ nguyên.

Ta có thể chứng minh cả ba bằng quy nạp theo số lần thao tác: ban đầu mỗi nút tự trỏ về mình; mỗi lần hợp nhất chỉ nối **hai gốc khác nhau**; nén đường đi chỉ chuyển cha của nút về gốc **cũ của cùng nhóm**.

## 3. `find` và tối ưu nén đường đi

Cách tìm gốc đơn giản là lần theo `parent[x]` cho đến khi thấy một nút tự trỏ về chính nó. Nếu hình dạng cây là một chuỗi dài, truy vấn có thể chậm.

**Nén đường đi (path compression)** làm cho các nút đã thăm trỏ trực tiếp đến gốc, rút ngắn đường đi của các truy vấn sau. Ví dụ, một đường `6 → 4 → 2 → 0` được nén thành `6 → 0`, `4 → 0`, `2 → 0` sau khi tìm gốc từ `6`.

Đoạn mã thường dùng:

```java
int find(int x) {
    if (parent[x] != x) {
        parent[x] = find(parent[x]);
    }
    return parent[x];
}
```

Lệnh `parent[x] = find(parent[x])` thực hiện **hai việc**: tìm đại diện của nhóm và cập nhật con trỏ cha để giảm số bước tìm lần sau. Nó **không** đưa phần tử sang nhóm khác.

Với bản đệ quy, độ sâu lời gọi phụ thuộc chiều cao cây trước nén. Nếu luôn **gộp theo kích thước** như phần sau, chiều cao cây bị chặn ở `O(log n)`; nhờ vậy ví dụ Java an toàn hơn nhiều so với kiểu gắn cha tùy tiện. Trong môi trường có yêu cầu cứng về ngăn xếp, có thể triển khai `find` bằng vòng lặp.

## 4. `union` và tối ưu hợp nhất theo kích thước

Hợp nhất hai phần tử `a,b` phải **tìm gốc trước**, rồi mới nối hai cây:

1. `rootA = find(a)` và `rootB = find(b)`.
2. Nếu `rootA == rootB`, trả `false`: chúng đã cùng nhóm.
3. Nếu khác nhau, cho gốc của **nhóm nhỏ** trỏ đến gốc của **nhóm lớn**.
4. Cộng kích thước của hai nhóm tại **gốc mới** và trừ một ở bộ đếm nhóm.

Đây là **union by size**. Nó tránh tình trạng cứ gắn một cây lớn xuống dưới cây nhỏ, làm chuỗi cha ngày càng dài. Khi độ sâu một nút tăng một mức do gộp theo kích thước, kích thước nhóm chứa nút đó ít nhất tăng gấp đôi; do nhóm không thể lớn hơn `n`, số lần độ sâu tăng bị chặn theo `log₂ n`.

Một cách gần tương đương là **union by rank**, dùng một đại lượng xấp xỉ giới hạn chiều cao cây để chọn gốc. **Rank khác kích thước nhóm**. Sau path compression, rank cũng không nhất thiết phản ánh chiều cao thật. Chọn union by size hoặc union by rank và giữ quy tắc cập nhật nhất quán; không nhầm hai mảng này.

Đặc biệt, **không dùng `parent[a] = b` trực tiếp** khi chưa tìm gốc. `a` và `b` có thể là nút ở giữa cây; phép gán đó có thể làm sai quan hệ nhóm hoặc tạo chu trình cha.

## 5. Chương trình Java 17+ đầy đủ

Ví dụ kết hợp **path compression + union by size**. Các phần tử nằm trong khoảng chỉ số `[0,n)`; truy cập chỉ số ngoài khoảng bị từ chối rõ ràng.

Lưu toàn bộ chương trình sau vào **`DSUDemo.java`**.

```java
public final class DSUDemo {
    private static final class DSU {
        private final int[] parent;
        private final int[] size;
        private int components;

        DSU(int n) {
            if (n < 0) {
                throw new IllegalArgumentException("n must be >= 0");
            }

            parent = new int[n];
            size = new int[n];
            components = n;

            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            if (x < 0 || x >= parent.length) {
                throw new IndexOutOfBoundsException("invalid element: " + x);
            }

            if (parent[x] != x) {
                parent[x] = find(parent[x]); // Nén đường đi.
            }
            return parent[x];
        }

        boolean union(int a, int b) {
            int rootA = find(a);
            int rootB = find(b);

            if (rootA == rootB) {
                return false;
            }

            // Gắn gốc của cây nhỏ vào gốc của cây lớn.
            if (size[rootA] < size[rootB]) {
                int temp = rootA;
                rootA = rootB;
                rootB = temp;
            }

            parent[rootB] = rootA;
            size[rootA] += size[rootB];
            components--;
            return true;
        }

        boolean connected(int a, int b) {
            return find(a) == find(b);
        }

        int componentSize(int x) {
            return size[find(x)];
        }

        int count() {
            return components;
        }
    }

    public static void main(String[] args) {
        DSU dsu = new DSU(7); // 0,1,2,3,4,5,6.

        System.out.println("So nhom ban dau: " + dsu.count());
        System.out.println("Gop 0-1: " + dsu.union(0, 1));
        System.out.println("Gop 1-2: " + dsu.union(1, 2));
        System.out.println("Gop 3-4: " + dsu.union(3, 4));
        System.out.println("0 va 2: " + dsu.connected(0, 2));
        System.out.println("2 va 4: " + dsu.connected(2, 4));
        System.out.println("Gop 2-4: " + dsu.union(2, 4));
        System.out.println("Gop lai 0-3: " + dsu.union(0, 3));
        System.out.println("Kich thuoc nhom chua 4: " + dsu.componentSize(4));
        System.out.println("So nhom cuoi: " + dsu.count());
        System.out.println("0 va 4: " + dsu.connected(0, 4));
    }
}
```

Dùng JDK 17 hoặc mới hơn:

```bash
javac DSUDemo.java
java DSUDemo
```

Kết quả chuẩn:

```text
So nhom ban dau: 7
Gop 0-1: true
Gop 1-2: true
Gop 3-4: true
0 va 2: true
2 va 4: false
Gop 2-4: true
Gop lai 0-3: false
Kich thuoc nhom chua 4: 5
So nhom cuoi: 3
0 va 4: true
```

Diễn tiến: ba lần hợp nhất đầu tạo các nhóm `{0,1,2}`, `{3,4}`, `{5}`, `{6}`. `union(2,4)` hợp nhất hai nhóm có kích thước `3` và `2` thành một nhóm năm phần tử. `union(0,3)` lúc này trả `false` vì đã cùng nhóm, nên số nhóm không đổi: ba nhóm `{0,1,2,3,4}`, `{5}` và `{6}`.

Đặc điểm của mã:

- `union` trả `boolean` để dễ kiểm tra có thực sự hợp nhất không; nhiều API khác có thể trả `void`, nhưng quy tắc bên trong không đổi.
- `componentSize` phải truy cập `size[find(x)]`, không phải `size[x]`. Kích thước ở nút không còn là gốc có thể là giá trị cũ.
- `count()` chỉ đúng vì khi `rootA != rootB` mới trừ một.
- `DSU(0)` hợp lệ và có `count() == 0`; `find(0)` trong DSU rỗng ném ngoại lệ.
- Các phép toán sửa mảng nội bộ và không được đồng bộ cho nhiều luồng; nếu sử dụng đồng thời, cần một cơ chế bảo vệ thích hợp.

## 6. Tính đúng của DSU: chứng minh bằng bất biến

**Khởi tạo:** mỗi `parent[i] = i` nên có `n` cây một nút. `size[i] = 1` và `components = n` là chính xác.

**Find:** đường đi từ nút đến gốc là duy nhất vì mọi nhóm là cây. Hàm trả gốc đó. Việc rút ngắn đường cha chỉ trỏ nút đến đúng gốc hiện có, nên giữ nguyên quan hệ cùng nhóm. Nó cũng không tạo chu trình vì gốc vẫn tự trỏ về mình và các nút khác chỉ trỏ về tổ tiên/gốc.

**Union khi gốc bằng nhau:** hai phần tử thuộc cùng nhóm; trả `false` mà không đổi phân hoạch, kích thước hay bộ đếm là đúng.

**Union khi gốc khác nhau:** hai gốc thuộc hai cây không giao nhau. Cho một gốc trỏ đến gốc còn lại nối hai cây thành một, không thể sinh chu trình vì trước đó hai cây độc lập. Thành viên nhóm mới đúng bằng hợp của hai nhóm cũ, kích thước gốc mới là tổng hai kích thước và số nhóm giảm đúng một.

Quy nạp theo chuỗi thao tác cho thấy mọi lúc `find(a) == find(b)` khi và chỉ khi `a,b` thuộc cùng nhóm được xác định bởi các lần hợp nhất đã diễn ra. Thứ tự hợp nhất có thể thay đổi **giá trị gốc đại diện** nhưng không thay đổi đáp án “cùng nhóm” sau cùng nếu tập các phép hợp nhất là như nhau.

## 7. Phân tích độ phức tạp

Đặt `n` là số phần tử được khởi tạo, `m` là số thao tác sau khởi tạo; `α(n)` là **hàm Ackermann nghịch đảo**, tăng cực kỳ chậm.

| Phần việc | Thời gian | Bộ nhớ |
|---|---|---|
| Khởi tạo hai mảng | `Θ(n)` | `Θ(n)` |
| `find(x)` với cả hai tối ưu | `O(α(n))` **khấu hao** | Tối đa `O(log n)` ngăn xếp trong bản đệ quy này |
| `union(a,b)` với cả hai tối ưu | `O(α(n))` **khấu hao** | Gọi `find` hai lần và dùng vài biến phụ |
| `connected(a,b)` | `O(α(n))` **khấu hao** | Gọi `find` hai lần |
| `componentSize(x)` | `O(α(n))` **khấu hao** | Gọi `find` một lần |
| `count()` | `Θ(1)` | `Θ(1)` |

Với **path compression** và **union by size/rank**, cách viết quen thuộc cho tổng thời gian khởi tạo và `m` thao tác là `O(n + m · α(n))`. Với kích thước dữ liệu thực tế, `α(n)` rất nhỏ nên hiệu năng thường được gọi là **gần hằng số khấu hao**. Cần hiểu chính xác: khấu hao là giới hạn **trung bình trên một chuỗi thao tác**, không chứng minh từng thao tác riêng lẻ chắc chắn tốn `O(1)` trong trường hợp xấu nhất.

Nếu chỉ dùng union by size, độ sâu cây có chặn trên `O(log n)`, vì khi độ sâu một nút tăng, nhóm chứa nó ít nhất gấp đôi kích thước. Vì vậy một `find` đơn lẻ có thời gian xấu nhất `O(log n)` ngay cả trước khi nén đường đi. Nếu không có quy tắc gộp tốt, cây có thể thành chuỗi dài `Θ(n)` khiến một lần tìm tốn `Θ(n)`.

**Bộ nhớ** cho hai mảng `parent[]` và `size[]` là `Θ(n)`. Bản `find` đệ quy còn dùng ngăn xếp với độ sâu tối đa `O(log n)` nhờ union by size; bản vòng lặp có thể giảm bộ nhớ phụ mỗi thao tác xuống `O(1)`. Nếu bài toán phải lưu riêng `E` cạnh đồ thị, cần cộng thêm phần lưu trữ đó; DSU không tự giữ danh sách cạnh.

Ví dụ, `n = 1.000.000`: hai mảng `int[]` dùng `2 × 1.000.000 × 4 = 8.000.000` byte dữ liệu phần tử, **chưa tính** phần đầu đối tượng, căn chỉnh, dữ liệu chương trình, các mảng/cạnh khác và bộ nhớ JVM. Ký hiệu `O(n)` không thay thế việc ước lượng byte khi RAM có giới hạn.

## 8. Các ứng dụng tiêu biểu

### 8.1. Thành phần liên thông trong đồ thị vô hướng chỉ thêm cạnh

Mỗi đỉnh là một phần tử của DSU. Khi thêm cạnh vô hướng `(u,v)`, gọi `union(u,v)`. Khi hỏi có đường nối (không nhất thiết trực tiếp) từ `a` đến `b` hay không, gọi `connected(a,b)`.

```text
ADD 0 1     -> gộp 0 với 1
ADD 1 2     -> gộp 1 với 2
ASK 0 2     -> true
ASK 0 3     -> false
ADD 2 3     -> gộp hai thành phần
ASK 0 3     -> true
```

Với một đồ thị cố định và chỉ vài truy vấn, BFS/DFS cũng có thể đủ đơn giản. DSU trở nên hấp dẫn khi có **nhiều truy vấn cùng thành phần** xen kẽ với **thêm liên kết**. Để tìm **đường đi cụ thể** hoặc **đường đi ngắn nhất**, cần thêm thuật toán/cấu trúc khác; DSU chỉ trả quan hệ cùng thành phần.

### 8.2. Phát hiện cạnh tạo chu trình trong đồ thị vô hướng

Khi xét một cạnh mới `(u,v)`:

- Nếu `find(u) != find(v)`, cạnh nối hai thành phần khác nhau và không tạo chu trình; `union(u,v)` trả `true`.
- Nếu `find(u) == find(v)`, giữa hai đầu đã có đường nối theo những cạnh đã xét; thêm cạnh ấy tạo một chu trình trong đồ thị vô hướng (với cách hiểu cạnh song song phù hợp của đồ thị đa cạnh).

Không dùng trực tiếp điều kiện này để kết luận **chu trình có hướng** trong đồ thị có hướng. Quan hệ “có đường đi theo chiều mũi tên” không đối xứng nên khác quan hệ nhóm mà DSU lưu.

### 8.3. Kruskal cho cây khung nhỏ nhất

Trong đồ thị vô hướng có trọng số, thuật toán **Kruskal** sắp xếp cạnh theo trọng số không giảm rồi lần lượt xét cạnh. Chỉ nhận một cạnh khi `union(u,v)` trả `true`. Nhờ đó các cạnh được chọn không tạo chu trình và nối thêm những thành phần còn rời.

Giả mã:

```text
Sắp xếp các cạnh theo trọng số tăng dần
Khởi tạo DSU(n)
Với mỗi cạnh (u, v, weight):
    Nếu union(u, v) trả true:
        Chọn cạnh vào rừng khung
        Cộng weight vào tổng
Dừng khi đã chọn n - 1 cạnh hoặc hết cạnh
```

Nếu đồ thị **liên thông**, ta được cây khung nhỏ nhất gồm `n - 1` cạnh. Nếu đồ thị **không liên thông**, kết quả là **rừng khung nhỏ nhất**; không được gọi đó là một cây khung của toàn đồ thị. Chi phí thường do bước sắp xếp `E` cạnh, khoảng `O(E log E)`, chi phối; các thao tác DSU bổ sung gần tuyến tính.

### 8.4. Giới hạn: DSU cơ bản không hỗ trợ tách nhóm

Một khi hai nhóm đã gộp, bản DSU thông thường **không có phép đảo `union`**. Nếu xóa một cạnh trong đồ thị, hai đỉnh có thể vẫn kết nối qua đường khác, hoặc thành phần có thể bị tách. DSU đang có không đủ thông tin để quyết định và cập nhật đúng.

Một số bài toán có thể xử lý xóa cạnh **ngoại tuyến** bằng cách đảo thứ tự sự kiện, hoặc dùng **rollback DSU** hay cấu trúc đồ thị động nâng cao. Những phương pháp đó có điều kiện và cách cài đặt riêng; không thể chỉ thêm hàm `remove` vào DSU ở ví dụ.

DSU cũng không tự cung cấp danh sách thành viên có thứ tự, đường đi, khoảng cách ngắn nhất, số cạnh trong mỗi nhóm hay thao tác truy vấn có hướng. Chỉ thêm các tổng hợp nhóm như kích thước/tổng/thuộc tính nếu bài toán cần và có quy tắc cập nhật đúng khi gộp.

## 9. Lỗi thường gặp và cách kiểm tra

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `parent[a] = b` khi `a,b` chưa chắc là gốc | Có thể sai nhóm hoặc sinh chu trình cha | Luôn tìm `rootA` và `rootB` trước |
| Trừ `components` dù hai gốc bằng nhau | Sai số nhóm khi gộp lặp | Chỉ trừ sau khi thực sự nối hai cây |
| Dùng `size[x]` tại nút không phải gốc | Kích thước có thể đã cũ | Dùng `size[find(x)]` |
| Nhầm union by rank với union by size | Cập nhật sai đại lượng tối ưu | Chọn và dùng nhất quán một quy tắc |
| Coi `find(x)` phải luôn bằng `x` hoặc phần tử nhỏ nhất | Đại diện phụ thuộc lịch sử hợp nhất | Chỉ dựa vào việc hai kết quả `find` có bằng nhau |
| Sai quy ước chỉ số từ 1 hoặc 0 | Truy cập ngoài mảng, sai nhóm | Chuẩn hóa ID trước khi thao tác |
| Dùng DSU như thể có xóa cạnh | Kết nối sau xóa không còn đúng | Chọn phương pháp hỗ trợ đồ thị động |
| Quên tính RAM cho hai mảng và dữ liệu cạnh | Vượt bộ nhớ dù thao tác nhanh | Dự toán bằng byte và phân tích tổng dữ liệu |

Tập kiểm thử cơ bản nên có: `n=0` và `n=1`; `union(x,x)`; gộp lặp; một chuỗi nối gián tiếp; các nhóm có kích thước khác nhau; phần tử không phải gốc; chỉ số âm/vượt biên; các thứ tự gộp khác nhau nhưng cho cùng phân hoạch.

**Đối chứng hữu ích:** với `n` nhỏ, duy trì đồ thị vô hướng bằng danh sách kề, thêm cùng các cạnh vào đồ thị và DSU. Sau mỗi thao tác, chạy BFS/DFS để kiểm tra khả năng đi tới giữa các cặp đỉnh và so với `connected`. Đây là kiểm thử phát hiện lỗi tốt, nhưng bằng chứng tính đúng tổng quát vẫn dựa trên bất biến của rừng cây và phép hợp nhất.

## 10. Bài tập thực hành

**Bài 1 — Mô phỏng phân hoạch.** Có sáu phần tử `0..5`. Thực hiện `union(0,1)`, `union(2,3)`, `union(1,3)`, `union(4,5)`, `union(0,2)`. Hỏi còn bao nhiêu nhóm, `componentSize(3)` là bao nhiêu, và `union(2,0)` trả gì?

*Đáp án:* hai nhóm `{0,1,2,3}` và `{4,5}`; `componentSize(3) == 4`; `union(2,0) == false`.

**Bài 2 — Chứng minh.** Vì sao nối hai **gốc khác nhau** không tạo chu trình cha? Vì sao path compression vẫn giữ nguyên quan hệ cùng nhóm?

*Gợi ý:* hai cây trước khi hợp nhất không giao nhau; sau nén, mỗi nút vẫn trỏ trong chính cây ấy đến cùng gốc.

**Bài 3 — Chọn thuật toán.** Một hệ thống có hàng triệu truy vấn “hai máy có cùng mạng không?”, chỉ thêm kết nối và không cần tìm đường đi. Vì sao DSU phù hợp hơn việc chạy BFS từ đầu cho từng truy vấn? Điều gì thay đổi khi hệ thống thường xuyên **xóa** kết nối?

*Gợi ý:* DSU giữ phân hoạch để tái sử dụng qua truy vấn; với xóa cạnh, quan hệ nhóm có thể phải tách nhưng DSU cơ bản không xử lý được.

**Bài 4 — Độ phức tạp.** Nêu sự khác nhau giữa `O(log n)` trong chứng minh độ cao cây của union by size và `O(α(n))` **khấu hao** khi kết hợp thêm nén đường đi. Vì sao không nên viết “mọi lần `find` đều `O(1)`”?

*Gợi ý:* phân tích khấu hao xét tổng chi phí của chuỗi thao tác, khác giới hạn trường hợp xấu nhất cho một thao tác đơn lẻ.

**Bài 5 — Giới hạn bộ nhớ.** Với `n=1.000.000` và hai mảng `int[]`, ước tính dung lượng dữ liệu phần tử trong hai mảng trước khi cộng chi phí quản lý bộ nhớ của JVM và các cấu trúc khác.

*Đáp án:* `8.000.000` byte, xấp xỉ `8 MB` hoặc `7,63 MiB`.

## Ghi nhớ

**DSU = quản lý các nhóm được hợp nhất dần.** Mỗi nhóm là một cây, `find` trả về gốc đại diện, `union` nối hai **gốc khác nhau**, và `connected` so sánh hai đại diện. **Nén đường đi** làm đường tìm ngắn đi; **hợp nhất theo kích thước/rank** tránh cây quá cao. Kết hợp hai tối ưu cho hiệu năng gần hằng số **khấu hao**, với bộ nhớ lưu cấu trúc `Θ(n)`. Hãy phân biệt **cùng thành phần kết nối** với **có cạnh trực tiếp**, và nhớ rằng DSU cơ bản **không hỗ trợ xóa cạnh, tách nhóm hay truy xuất đường đi**.
