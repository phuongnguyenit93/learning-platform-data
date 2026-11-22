# Cây tìm kiếm có thứ tự và truy vấn theo miền giá trị

Một cấu trúc dữ liệu phục vụ tìm kiếm có thể cần trả lời nhiều hơn câu hỏi “khóa x có tồn tại không?”. Chẳng hạn, hệ thống cần tìm giá gần nhất không vượt ngân sách, lấy mọi sự kiện diễn ra từ ngày a đến ngày b, đếm bao nhiêu bản ghi có điểm trong một khoảng, hoặc tìm phần tử đứng thứ k theo thứ tự tăng dần.

**Cây tìm kiếm có thứ tự (ordered search tree)** tổ chức khóa theo quan hệ thứ tự để hỗ trợ các truy vấn này. Bài học tập trung vào cây tìm kiếm nhị phân có thứ tự, phiên bản tự cân bằng, các truy vấn trên miền giá trị và cách áp dụng trong Java 17.

## 1. Vì sao cần cấu trúc có thứ tự?

Với một bảng băm, tra một khóa chính xác thường nhanh, nhưng bảng băm thông thường không duy trì các khóa theo thứ tự. Một truy vấn như “khóa nhỏ nhất lớn hơn hoặc bằng 25” hoặc “mọi khóa trong [20, 50]” không thể dựa vào việc sắp xếp có sẵn của bảng băm.

Với một mảng đã sắp xếp, có thể tìm hai biên bằng tìm kiếm nhị phân và đọc các phần tử trong khoảng rất hiệu quả. Tuy nhiên, chèn hoặc xóa một phần tử ở giữa mảng thường phải dịch chuyển O(n) phần tử.

Cây tìm kiếm có thứ tự hướng đến tình huống **dữ liệu thay đổi trong khi vẫn cần tìm khóa, tìm hàng xóm theo thứ tự và quét khoảng giá trị**. Nếu cây được giữ cân bằng, các thao tác định vị cơ bản có thể hoàn thành trong O(log n).

## 2. Bất biến thứ tự của cây tìm kiếm nhị phân

Với một nút có khóa **k**, cây tìm kiếm nhị phân (binary search tree, BST) dùng bất biến:

- Tất cả khóa trong cây con trái **nhỏ hơn k**.
- Tất cả khóa trong cây con phải **lớn hơn k**.
- Hai cây con cũng tuân thủ chính bất biến đó.

Quy ước trên giả sử mỗi nút chứa một **khóa phân biệt**. Nếu dữ liệu có khóa lặp, một cách xử lý là giữ **frequency** (số lần xuất hiện) tại cùng một nút. Một thiết kế khác có thể gắn danh sách bản ghi vào một khóa. Cần nêu rõ quy ước vì nó quyết định kết quả của phép đếm và phép chọn phần tử thứ k.

Ví dụ, các khóa phân biệt 1, 3, 4, 6, 7, 8, 10 có thể nằm trong cây:

~~~text
          6
        /   \
       3     8
      / \   / \
     1   4 7  10
~~~

Duyệt cây theo thứ tự **trái → nút → phải** (in-order) cho dãy khóa tăng dần: **1, 3, 4, 6, 7, 8, 10**.

Dạng hình của cây không cố định: nhiều cây khác nhau có thể biểu diễn cùng một tập khóa. Điểm cốt lõi là bất biến thứ tự, không phải nút nào phải nằm ở vị trí nào.

**Không phải BST nào cũng tự cân bằng.** Nếu chèn 1, 2, 3, 4, 5 lần lượt vào BST thông thường mà không tái cân bằng, cây có thể trở thành một chuỗi cao n. Khi đó tìm kiếm, chèn, xóa mất O(n) trong trường hợp xấu nhất.

Các cấu trúc tự cân bằng như **AVL tree** và **red-black tree** giữ chiều cao O(log n) bằng những quy tắc cân bằng và phép xoay phù hợp. Trong Java, **TreeMap** được triển khai dựa trên red-black tree; **TreeSet** dựa trên TreeMap.

## 3. Những thao tác tìm kiếm có thứ tự

Giả sử tập khóa phân biệt đang có là **{1, 3, 4, 6, 7, 8, 10, 13, 14}**.

| Thao tác | Ý nghĩa | Ví dụ với x = 6 |
| --- | --- | --- |
| **contains(x)** | Có khóa bằng x không? | true |
| **lower(x)** | Khóa lớn nhất **nhỏ hơn x** | 4 |
| **floor(x)** | Khóa lớn nhất **nhỏ hơn hoặc bằng x** | 6 |
| **ceiling(x)** | Khóa nhỏ nhất **lớn hơn hoặc bằng x** | 6 |
| **higher(x)** | Khóa nhỏ nhất **lớn hơn x** | 7 |
| **first / last** | Khóa nhỏ nhất / lớn nhất | 1 / 14 |
| **successor / predecessor** | Kế tiếp / trước đó theo thứ tự | Tương ứng higher / lower với khóa phân biệt |

Sự khác nhau giữa dấu **nhỏ hơn** và **nhỏ hơn hoặc bằng** rất quan trọng. Chẳng hạn với x = 5, **floor(5) = 4**, **ceiling(5) = 6**; với x = 6, **lower(6) = 4**, còn **floor(6) = 6**.

Nếu không có khóa thỏa điều kiện, các phương thức điều hướng tương ứng của Java TreeMap như **lowerKey**, **floorKey**, **ceilingKey** và **higherKey** trả về **null**. Trong ứng dụng có thể dùng null để biểu thị “không tồn tại”, nhưng phải xử lý trường hợp này trước khi sử dụng kết quả như một số nguyên.

### Tìm lower bound và upper bound

Trong thuật toán trên mảng sắp xếp, **lower bound của x** thường là vị trí đầu tiên có phần tử ≥ x; **upper bound của x** là vị trí đầu tiên có phần tử > x. Trong cây có thứ tự, các khóa tương ứng là **ceiling(x)** và **higher(x)** nếu tồn tại.

Đừng nhầm **upper bound** kiểu “phần tử đầu tiên > x” với **biên trên của một khoảng truy vấn** có thể được chọn đóng hoặc mở. Muốn làm rõ phải viết điều kiện bằng dấu so sánh.

## 4. Truy vấn theo miền giá trị (range query)

Một truy vấn khoảng cho hai mốc **a, b** và trả về các khóa hoặc bản ghi có khóa nằm trong khoảng được chỉ định.

- **[a, b]**: a ≤ key ≤ b, đóng ở hai đầu.
- **[a, b)**: a ≤ key < b, đóng trái, mở phải.
- **(a, b]**: a < key ≤ b, mở trái, đóng phải.
- **(a, b)**: a < key < b, mở ở hai đầu.

Trong lập trình, ranh giới mở/đóng là một phần của đặc tả đầu ra. Ví dụ với các khóa **1, 3, 4, 6, 7, 8, 10, 13, 14**:

- **[4, 10]** trả **4, 6, 7, 8, 10**.
- **[4, 10)** trả **4, 6, 7, 8**.
- **(4, 10)** trả **6, 7, 8**.

Nếu a > b, miền giá trị theo nghĩa toán học là rỗng. Khi dùng API Java **subMap**, không được truyền biên đảo ngược mà chưa xử lý, vì API có thể ném **IllegalArgumentException**.

### Cách BST loại bỏ nhánh không cần xét

Để liệt kê khóa thuộc **[a, b]**, tại nút có khóa k:

1. Chỉ duyệt cây con trái nếu **k > a**, bởi các khóa trong cây con trái đều nhỏ hơn k.
2. Xuất khóa k nếu **a ≤ k ≤ b**.
3. Chỉ duyệt cây con phải nếu **k < b**, bởi các khóa trong cây con phải đều lớn hơn k.

Cần giữ đúng thứ tự **trái → nút → phải** để kết quả tăng dần. Nếu nút chỉ chứa một khóa và frequency, lúc xuất nút phải quyết định xuất khóa **một lần** hay xuất một bản ghi cho **mỗi lần xuất hiện**.

~~~text
range(node, a, b):
    if node == null:
        return
    if node.key > a:
        range(node.left, a, b)
    if a <= node.key and node.key <= b:
        emit(node.key)
    if node.key < b:
        range(node.right, a, b)
~~~

Đây là giả mã cho cây **không có khóa trùng ở các nút riêng biệt**. Khi cài đặt theo quy ước khác, điều kiện cắt nhánh có thể phải điều chỉnh.

Với cây cân bằng có **m khóa phân biệt**, việc tìm điểm bắt đầu rồi xuất **r khóa** liên tiếp có độ phức tạp **O(log m + r)**. Khi cần in toàn bộ r kết quả, bản thân đầu ra đã cần Ω(r) thao tác. Với BST không cân bằng, chiều cao h có thể tới m; một cách biểu diễn tổng quát cho thao tác liệt kê khoảng trên cây thứ tự là **O(h + r)** trong triển khai có cắt nhánh hiệu quả.

## 5. Bài toán có khóa lặp: đếm bản ghi và đếm khóa

Xét 10 số: **[8, 3, 10, 1, 6, 14, 4, 7, 13, 6]**. Giá trị **6 xuất hiện hai lần**. Nếu dùng mỗi khóa của TreeMap ánh xạ đến số lần xuất hiện, ta được:

| Khóa | 1 | 3 | 4 | 6 | 7 | 8 | 10 | 13 | 14 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tần suất | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | 1 |

Trong khoảng **[4, 10]**:

- **Số khóa phân biệt** là **5**: 4, 6, 7, 8, 10.
- **Số bản ghi/số lần xuất hiện** là **6**: 1 + 2 + 1 + 1 + 1.
- **Số khóa nhỏ hơn hoặc bằng 6, tính cả lần lặp**, là **5**: 1 + 1 + 1 + 2.
- Phần tử **thứ 6** của đa tập khi sắp tăng dần (đánh số từ 1) là **7**.

Điều này phân biệt hai đại lượng thường bị nhầm lẫn:

- **Distinct count**: số khóa khác nhau.
- **Total count**: tổng frequency trên các khóa.

Nếu bài toán quản lý nhiều bản ghi cùng giá, cùng ngày hoặc cùng điểm số, chọn sai một trong hai cách đếm sẽ cho kết quả sai dù thao tác trên cây đúng.

## 6. Java 17+: TreeMap, điều hướng và lọc khoảng

**TreeMap<K,V>** duy trì các khóa theo thứ tự tăng dần theo **Comparable** tự nhiên hoặc theo **Comparator** được cấp khi khởi tạo. **NavigableMap** cung cấp các thao tác điều hướng và các view của khoảng khóa.

Ví dụ đầy đủ dưới đây thống kê tần suất của các số nguyên. Dữ liệu có khóa lặp, nên giữ tổng số lần xuất hiện trong value thay vì cố chèn nhiều nút có cùng key.

~~~java
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class OrderedRangeQueryDemo {
    public static void main(String[] args) {
        int[] input = {8, 3, 10, 1, 6, 14, 4, 7, 13, 6};
        NavigableMap<Integer, Integer> frequency = new TreeMap<>();

        for (int x : input) {
            frequency.merge(x, 1, Integer::sum);
        }

        System.out.println("Tan suat: " + frequency);
        System.out.println("floor(5): " + frequency.floorKey(5));
        System.out.println("ceiling(5): " + frequency.ceilingKey(5));
        System.out.println("lower(6): " + frequency.lowerKey(6));
        System.out.println("higher(6): " + frequency.higherKey(6));

        NavigableMap<Integer, Integer> inclusive =
                frequency.subMap(4, true, 10, true);
        NavigableMap<Integer, Integer> halfOpen =
                frequency.subMap(4, true, 10, false);

        System.out.println("Khoa [4,10]: " + inclusive.navigableKeySet());
        System.out.println("Khoa [4,10): " + halfOpen.navigableKeySet());
        System.out.println("So khoa [4,10]: " + inclusive.size());
        System.out.println("So phan tu [4,10]: "
                + countInclusive(frequency, 4, 10));
        System.out.println("So phan tu <= 6: "
                + countAtMost(frequency, 6));
        System.out.println("Phan tu thu 6: "
                + selectByFrequency(frequency, 6));

        // Xóa đúng một lần xuất hiện của khóa 6.
        frequency.computeIfPresent(6,
                (key, count) -> count == 1 ? null : count - 1);
        System.out.println("Tan suat cua 6 sau xoa: " + frequency.get(6));
    }

    private static long countInclusive(
            NavigableMap<Integer, Integer> frequency, int low, int high) {
        if (low > high) {
            return 0L;
        }

        long total = 0L;
        for (int count : frequency.subMap(low, true, high, true).values()) {
            total += count;
        }
        return total;
    }

    private static long countAtMost(
            NavigableMap<Integer, Integer> frequency, int upper) {
        long total = 0L;
        for (int count : frequency.headMap(upper, true).values()) {
            total += count;
        }
        return total;
    }

    // k đánh số từ 1, có tính các lần xuất hiện trùng khóa.
    // Trả null nếu k vượt tổng số phần tử.
    private static Integer selectByFrequency(
            NavigableMap<Integer, Integer> frequency, long k) {
        if (k <= 0) {
            throw new IllegalArgumentException("k phai duong");
        }

        for (Map.Entry<Integer, Integer> entry : frequency.entrySet()) {
            k -= entry.getValue();
            if (k <= 0) {
                return entry.getKey();
            }
        }
        return null;
    }
}
~~~

Lưu vào tệp **OrderedRangeQueryDemo.java** và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac OrderedRangeQueryDemo.java
java OrderedRangeQueryDemo
~~~

Đầu ra chính xác với dữ liệu trên:

~~~text
Tan suat: {1=1, 3=1, 4=1, 6=2, 7=1, 8=1, 10=1, 13=1, 14=1}
floor(5): 4
ceiling(5): 6
lower(6): 4
higher(6): 7
Khoa [4,10]: [4, 6, 7, 8, 10]
Khoa [4,10): [4, 6, 7, 8]
So khoa [4,10]: 5
So phan tu [4,10]: 6
So phan tu <= 6: 5
Phan tu thu 6: 7
Tan suat cua 6 sau xoa: 1
~~~

Giải thích:

- **merge** tăng tần suất cho khóa đã tồn tại hoặc gán 1 cho khóa mới.
- **floorKey/ceilingKey/lowerKey/higherKey** trả các khóa theo điều kiện thứ tự đã nêu.
- **subMap(4, true, 10, true)** lấy miền [4, 10], còn **subMap(4, true, 10, false)** lấy [4, 10). Hai đối số boolean thể hiện việc **bao gồm** hay **loại trừ** biên.
- **inclusive.size()** là số **khóa phân biệt** trong view. Muốn đếm bản ghi, hàm **countInclusive** phải cộng các frequency.
- **headMap(6, true)** lấy các khóa ≤ 6. Hàm **countAtMost** cộng tần suất từ view này.
- **selectByFrequency** duyệt khóa tăng dần, trừ số lần xuất hiện cho tới vị trí k. Đây là cách minh họa dễ hiểu, **chưa phải** cấu trúc chọn hạng O(log m).
- **computeIfPresent** giảm tần suất 6 từ 2 xuống 1. Khi tần suất về 0, lambda trả null để xóa hẳn cặp khóa–giá trị; điều đó giữ cho bảng chỉ chứa khóa có số lần xuất hiện dương.

### Điểm cần nhớ khi sử dụng API

**subMap, headMap và tailMap tạo view gắn với bản đồ gốc**, không phải bản sao dữ liệu. Nếu sửa bản đồ qua một view, bản đồ gốc cũng thay đổi; các thay đổi của bản đồ gốc cũng hiển thị qua view nếu nằm trong miền tương ứng. Khi chỉ muốn dữ liệu độc lập, có thể tạo **new TreeMap<>(view)**.

Khóa của TreeMap được quyết định bởi **thứ tự so sánh**, không phải bởi hashCode. Nếu Comparator coi hai khóa là bằng nhau (kết quả compare = 0), TreeMap xử lý chúng là cùng một khóa, dù theo cách hiểu nghiệp vụ chúng có thể khác nhau. Comparator phải nhất quán và ổn định; không thay đổi những thuộc tính dùng để so sánh của khóa đang nằm trong cây.

TreeMap không bảo đảm một bản ghi tồn tại cho mỗi khóa lặp: đặt giá trị mới bằng **put** trên khóa đã có sẽ **thay thế value cũ**. Cần chủ động thiết kế frequency hoặc danh sách bản ghi nếu muốn giữ nhiều lần xuất hiện.

## 7. Hiểu đúng độ phức tạp của từng truy vấn

Gọi **m** là số khóa phân biệt trong cây và **r** là số khóa phân biệt thực sự được trả về trong một khoảng.

| Thao tác | TreeMap cân bằng | Giải thích |
| --- | --- | --- |
| Tìm kiếm, chèn, xóa một khóa | O(log m) | Tìm vị trí theo chiều cao cây |
| floor, ceiling, lower, higher | O(log m) | Tìm khóa gần nhất thỏa điều kiện |
| Định vị đầu khoảng rồi duyệt r khóa | O(log m + r) | Tìm biên và lần lượt duyệt nút kế tiếp |
| Đếm khóa phân biệt trong khoảng bằng vòng lặp | O(log m + r) | Mỗi khóa trong khoảng phải được duyệt |
| Cộng frequency trong khoảng bằng ví dụ Java | O(log m + r) | Không có tổng subtree để bỏ qua cả nhánh |
| Chọn phần tử thứ k bằng ví dụ Java | O(m) | Duyệt entry từ đầu đến khi đủ tần suất |
| Lưu trữ TreeMap với m khóa | O(m) | Mỗi khóa phân biệt có một entry, chưa tính dữ liệu value tham chiếu |

**Lưu ý:** Các thao tác như **size()** trên một view của NavigableMap không được mặc định coi là O(1). Với yêu cầu truy vấn tổng hợp nhiều lần, cần kiểm tra cấu trúc dữ liệu được dùng và liệu nó có lưu metadata cho truy vấn đó không.

Đối với BST không cân bằng, thay **log m** bằng chiều cao **h** của cây khi phân tích các thao tác tìm kiếm vị trí; trường hợp xấu nhất có thể là **h = m**. Một cây có thứ tự nhưng không duy trì cân bằng không bảo đảm tốc độ logarit.

Nếu tập khóa tĩnh, có thể dùng **mảng sắp xếp** và hai phép tìm kiếm nhị phân: **lowerBound(a)** và **upperBound(b)**. Số phần tử trong [a,b] bằng **upperBound(b) − lowerBound(a)**, kể cả phần tử lặp nếu mỗi lần xuất hiện chiếm một phần tử mảng. Khi đó đếm khoảng chỉ mất O(log n) mà không cần duyệt tất cả phần tử. Đổi lại, chèn/xóa vào mảng thường tốn O(n).

## 8. Tăng cường cây để trả lời đếm khoảng trong O(log n)

Nếu có rất nhiều truy vấn **“bao nhiêu phần tử nằm trong [a,b]?”** trên tập dữ liệu thường xuyên thay đổi, không nên cộng frequency bằng vòng lặp mỗi lần.

Một **order-statistic tree** (cây có thông tin thứ hạng) tăng cường mỗi nút với:

- **key**: khóa của nút.
- **frequency**: số lần khóa xuất hiện, tối thiểu 1.
- **subtreeCount**: tổng số lần xuất hiện của tất cả khóa trong cây con gốc tại nút này.

Bất biến bổ sung là:

**subtreeCount(node) = subtreeCount(left) + frequency(node) + subtreeCount(right)**,

trong đó subtreeCount(null) = 0.

Nhờ đó có thể bỏ qua toàn bộ cây con và dùng số lượng đã được lưu sẵn. Ví dụ, để đếm **bao nhiêu phần tử có khóa < x**, bắt đầu ở gốc:

1. Nếu **x ≤ node.key**, tiếp tục sang trái; không có phần tử nào tại nút hiện tại hoặc bên phải đủ nhỏ.
2. Nếu **x > node.key**, cộng **subtreeCount(node.left) + frequency(node)** rồi sang phải.
3. Khi gặp null, tổng đã cộng là kết quả **countLessThan(x)**.

Để tính **countLessOrEqual(x)**, thay điều kiện sang trái bằng **x < node.key**; tại bước còn lại cộng nhánh trái và frequency của nút hiện tại.

Suy ra, với **a ≤ b**:

**countInRange(a, b) = countLessOrEqual(b) − countLessThan(a)**.

Công thức không cần tính **b + 1**, nên tránh được lỗi tràn số khi b là giá trị nguyên lớn nhất.

### Truy vấn phần tử thứ k (select)

Cho **k bắt đầu từ 1**, tại nút hiện tại tính L = subtreeCount(left):

- Nếu **k ≤ L**, đi sang trái.
- Nếu **L < k ≤ L + frequency**, trả khóa hiện tại.
- Nếu **k > L + frequency**, đi sang phải với **k mới = k − L − frequency**.

Với cây cân bằng có metadata đúng, **rank, countInRange và select** đều có thể chạy O(log m). Đây là khác biệt lớn so với phép quét tuyến tính các entry của TreeMap ở ví dụ.

### Cập nhật thông tin khi cây thay đổi

Khi chèn/xóa một khóa hoặc tăng/giảm frequency, phải cập nhật subtreeCount trên đường đi lên gốc. Nếu cây tự cân bằng bằng phép xoay, **metadata của các nút tham gia xoay cũng phải được tính lại theo cấu trúc con mới**; chỉ chỉnh liên kết trái/phải mà quên metadata sẽ khiến mọi truy vấn rank/select sai.

Trong một phép xoay, cần tính lại nút vừa bị đẩy xuống **trước**, rồi mới tính lại nút ở vị trí gốc mới, vì tổng của nút phía trên phụ thuộc kết quả phía dưới.

**Java TreeMap không cung cấp sẵn API rank/select O(log m) hoặc subtreeCount.** Muốn tính hạng nhanh trên dữ liệu động, cần tự cài một cây cân bằng có tăng cường, dùng thư viện phù hợp, hoặc chọn một cấu trúc khác có hỗ trợ phép tổng hợp cần thiết.

## 9. Truy vấn khoảng dạng tổng, nhỏ nhất, lớn nhất

Không phải truy vấn miền giá trị nào cũng chỉ trả danh sách khóa.

Ví dụ:

- **rangeCount(a,b)**: đếm số bản ghi có khóa thuộc [a,b].
- **rangeSum(a,b)**: cộng giá trị gắn với các khóa trong [a,b].
- **rangeMin / rangeMax(a,b)**: tìm giá trị nhỏ nhất/lớn nhất trong miền khóa.
- **rangeReport(a,b)**: xuất toàn bộ bản ghi trong miền.
- **nearest(x)**: tìm khóa sát x nhất theo một cách đo cụ thể.

Có thể tăng cường nút BST bằng metadata phù hợp. Chẳng hạn nếu mỗi lần xuất hiện tại khóa k đóng góp trọng số w(k), ta lưu:

**subtreeWeight = weight(left) + frequency × w(key) + weight(right)**.

Khi đó truy vấn tổng theo khoảng có thể đổi thành **prefixSum(≤ b) − prefixSum(< a)**, tương tự phép đếm. Nếu weight có thể âm, phép cộng prefix vẫn đúng; nhưng một thuật toán cắt nhánh dựa trên tổng đơn điệu có thể không còn đúng.

Đối với **min/max** hoặc phép gộp kết hợp, metadata và cách cập nhật cũng phải tương thích với ý nghĩa của truy vấn. Không thể suy ra tổng, min, max hoặc thứ hạng chỉ từ thứ tự khóa nếu cây chưa lưu hoặc chưa tính thông tin tương ứng.

## 10. Chọn cấu trúc dữ liệu đúng cho bài toán

| Bối cảnh | Cấu trúc phù hợp | Lý do chính |
| --- | --- | --- |
| Khóa thay đổi; tìm predecessor/successor và liệt kê khoảng | **TreeMap / TreeSet**, AVL, red-black tree | Duy trì thứ tự cùng tìm kiếm O(log m) |
| Cần nhiều bản ghi trùng khóa | **TreeMap<key, frequency/list>** hoặc thiết kế đa tập | Xác định rõ ý nghĩa của “một khóa” và “một bản ghi” |
| Cần đếm khoảng và chọn thứ k nhanh khi cập nhật | **Order-statistic tree** | Dùng subtreeCount, rank và select |
| Dữ liệu chủ yếu tĩnh, chỉ cần tra cứu khoảng | **Mảng sắp xếp + binary search** | Đếm khoảng O(log n), quét kết quả tuần tự |
| Chỉ số nguyên thuộc miền hữu hạn; cập nhật điểm và tổng prefix | **Fenwick tree (Binary Indexed Tree)** | Cập nhật, tổng prefix O(log U) trên miền chỉ số kích thước U |
| Nhiều truy vấn tổng/min/max trên đoạn chỉ số | **Segment tree** | Gộp dữ liệu đoạn, cập nhật và truy vấn thường O(log U) |
| Tìm mọi khoảng [start,end] giao với khoảng yêu cầu | **Interval tree** hoặc cấu trúc khoảng chuyên dụng | Dữ liệu là **các đoạn**, không đơn thuần là khóa điểm |
| Dữ liệu rất lớn lưu trên đĩa; duyệt khoảng liên tục | **B-tree / B+ tree** | Thiết kế tận dụng khối I/O và tính địa phương dữ liệu |

**Fenwick tree và segment tree** thường đánh chỉ số theo vị trí 1..U hoặc 0..U−1. Nếu khóa là giá trị thưa như 100, 1000000, 500000000, có thể cần **nén tọa độ (coordinate compression)** để ánh xạ khóa sang vị trí. Nếu tập khóa mới xuất hiện liên tục, phải cân nhắc chi phí cập nhật ánh xạ hoặc dùng cấu trúc động.

Một **truy vấn khóa trong [a,b]** khác với **truy vấn các khoảng giao [a,b]**. Ví dụ, có một sự kiện bắt đầu lúc 2 và kết thúc lúc 9. Truy vấn các sự kiện đang diễn ra tại thời điểm 7 cần kiểm tra **start ≤ 7 ≤ end**; tìm khóa start nằm trong [7,7] bằng TreeMap sẽ bỏ sót sự kiện đó. Cần mô hình hóa đoạn và dùng giải pháp phù hợp.

Với dữ liệu hai chiều trở lên, chẳng hạn điểm có cả **x** và **y** nằm trong hình chữ nhật, một cây sắp thứ tự theo x không tự giải quyết hiệu quả toàn bộ điều kiện theo y. Có thể cần range tree đa chiều, k-d tree hoặc chỉ mục không gian tùy loại truy vấn.

## 11. Những lỗi phổ biến và cách tránh

1. **Nhầm BST thường với BST cân bằng.** Cây có tính thứ tự chưa bảo đảm chiều cao O(log n). Khi cần bảo đảm hiệu năng theo trường hợp xấu nhất, chọn cấu trúc tự cân bằng.
2. **Nhầm số khóa với số bản ghi.** TreeMap.size() phản ánh số entry/khóa, không tự cộng frequency.
3. **Sai biên đóng/mở.** Phải xác định chính xác [a,b], [a,b), (a,b] hay (a,b). Trong Java, truyền đúng hai boolean cho subMap.
4. **Đảo ngược biên.** Với low > high, tự xử lý khoảng rỗng theo đặc tả trước khi gọi subMap.
5. **Cho rằng TreeMap đếm khoảng O(log n).** TreeMap không lưu subtreeCount cho người dùng; đếm bằng vòng lặp qua view phụ thuộc số khóa được duyệt.
6. **Quên xử lý không có floor/ceiling.** Các hàm điều hướng có thể trả null khi không tồn tại khóa thỏa điều kiện.
7. **Đánh đồng view với bản sao.** Thay đổi qua subMap/headMap/tailMap ảnh hưởng bản đồ gốc; tạo bản sao khi cần cô lập dữ liệu.
8. **Comparator vi phạm tính nhất quán hoặc khóa bị biến đổi.** Thứ tự không ổn định có thể gây kết quả khó đoán, tìm không ra khóa hoặc thay thế entry không mong muốn.
9. **Làm sai metadata khi xoay cây.** Order-statistic tree trả rank sai nếu subtreeCount không được tính lại đúng sau thao tác chèn, xóa, xoay.
10. **Dùng phép cộng vượt giới hạn kiểu số.** Tổng tần suất hoặc trọng số có thể cần long hay BigInteger. Tránh trừ/cộng 1 vào biên nguyên tối đa chỉ để biến truy vấn đóng thành mở.
11. **Dùng cây điểm cho dữ liệu đoạn.** Truy vấn overlap/stabbing cần xét cả điểm đầu và điểm cuối của đoạn.
12. **Lựa chọn cấu trúc quá phức tạp.** Nếu không có cập nhật, mảng sắp xếp thường đủ tốt; nếu chỉ cần kiểm tra tồn tại mà không cần thứ tự, bảng băm có thể đơn giản hơn.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với các khóa {2, 5, 8, 11}, floor(7), ceiling(7), lower(5) và higher(8) lần lượt là gì?  
**Đáp án:** 5, 8, 2, 11.

**Câu 2.** Với dữ liệu [2, 2, 3, 5, 5, 5], khoảng [2, 5) chứa bao nhiêu khóa phân biệt và bao nhiêu phần tử?  
**Đáp án:** Hai khóa phân biệt {2,3}; có 3 phần tử nếu tính cả lần xuất hiện lặp.

**Câu 3.** Cần đếm số phần tử trong [a,b] sau nhiều lần chèn/xóa, mỗi truy vấn mong muốn O(log n). Chỉ duyệt subMap có đáp ứng không?  
**Đáp án:** Không nếu khoảng có nhiều khóa. Nên dùng cây cân bằng lưu subtreeCount hoặc cấu trúc tổng prefix phù hợp.

**Câu 4.** Vì sao tìm tất cả lịch hẹn có khoảng thời gian giao với [14:00,15:00] không thể chỉ duyệt các khóa thời điểm bắt đầu trong khoảng ấy?  
**Đáp án:** Lịch bắt đầu trước 14:00 nhưng kết thúc sau 14:00 vẫn giao với khoảng truy vấn. Phải kiểm tra hai đầu mút hoặc dùng chỉ mục khoảng.

**Câu 5.** Với tập khóa tĩnh đã sắp xếp, muốn đếm bao nhiêu phần tử nằm trong [a,b] cần thao tác gì?  
**Đáp án:** Tìm vị trí đầu tiên ≥ a và vị trí đầu tiên > b bằng binary search, lấy hiệu hai chỉ số. Việc này có O(log n) thời gian với mảng đã sắp xếp.

## 13. Ghi nhớ

**Cây tìm kiếm có thứ tự** cho phép định vị khóa và các hàng xóm theo quan hệ nhỏ hơn/lớn hơn; **cây cân bằng** bảo đảm đường đi tìm kiếm ngắn; **truy vấn khoảng** tận dụng thứ tự để bỏ qua nhánh không liên quan. Khi câu hỏi yêu cầu **đếm, tổng hợp hoặc tìm hạng**, cần phân biệt cách làm bằng **duyệt các khóa** với cấu trúc được **tăng cường metadata** để bỏ qua cả cây con. Hãy xác định rõ đối tượng cần truy vấn, biên đóng/mở, ý nghĩa khóa lặp, tần suất cập nhật và kích thước đầu ra trước khi chọn TreeMap, cây thống kê thứ tự, mảng sắp xếp, Fenwick tree, segment tree hay interval tree.