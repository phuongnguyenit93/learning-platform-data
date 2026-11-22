# TreeSet và cấu trúc cây tìm kiếm cân bằng

## 1. TreeSet giải quyết bài toán nào?

Một hệ thống quản lý các mốc thời gian cần giữ mỗi mốc một lần, duyệt theo thứ tự, kiểm tra một mốc đã có chưa, và tìm mốc gần nhất trước hoặc sau một giá trị. Dữ liệu còn được thêm và xóa trong lúc chương trình chạy.

Đó là tình huống phù hợp để cân nhắc `TreeSet`: tập hợp các phần tử được tổ chức theo một quan hệ thứ tự, có thể duy trì thứ tự khi dữ liệu thay đổi.

Ba ý cần tách biệt ngay từ đầu:

- **Tập hợp:** một giá trị được xem là đã có thì thêm lại không tạo thành viên mới.
- **Thứ tự:** các phần tử được duyệt theo thứ tự tự nhiên hoặc theo bộ so sánh đã chọn.
- **Cấu trúc cây cân bằng:** đường tìm kiếm được giữ ngắn, kể cả khi dữ liệu đầu vào vốn đã tăng dần.

“Được sắp xếp” không có nghĩa mỗi lần thêm một phần tử, TreeSet lấy toàn bộ dữ liệu ra và sắp xếp lại. Nó đặt phần tử vào một vị trí phù hợp trong cây, rồi điều chỉnh cấu trúc cục bộ khi cần.

Theo [tài liệu TreeSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), TreeSet là một triển khai `NavigableSet` dựa trên `TreeMap`; ba thao tác cơ bản `add`, `remove`, `contains` có bảo đảm chi phí logarit. [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) dùng cây đỏ–đen, một dạng cây tìm kiếm nhị phân tự cân bằng.

Bài này đi từ quy tắc tìm kiếm trong cây đến lý do phải cân bằng, sau đó nối cơ chế ấy với hành vi và chi phí của TreeSet. Không cần tự viết một cây đỏ–đen để dùng TreeSet, nhưng hiểu cấu trúc giúp chọn đúng API và tránh suy luận sai về hiệu năng.

## 2. Mối liên hệ giữa Set, SortedSet và NavigableSet

Có thể đọc các giao diện theo khả năng mà chúng bổ sung:

```text
Set<E>
    thành viên và tính duy nhất

SortedSet<E>
    thêm một thứ tự trên các phần tử

NavigableSet<E>
    thêm cách tìm phần tử lân cận và các biên

TreeSet<E>
    triển khai cụ thể dựa trên cây tìm kiếm cân bằng
```

TreeSet không phải List đã sắp xếp. Nó không có thao tác `get(index)` để lấy “phần tử thứ i” như List. Một cây có thứ tự không đương nhiên có thông tin đếm số phần tử ở từng cây con để hỗ trợ truy cập theo vị trí.

Một cách khai báo thường dùng là:

```java
// Trích đoạn; cần import java.util.NavigableSet và java.util.TreeSet.
NavigableSet<Integer> milestones = new TreeSet<>();
milestones.add(30);
milestones.add(10);
milestones.add(20);
```

Biến dùng giao diện `NavigableSet` vì mã gọi cần khả năng điều hướng theo thứ tự. Đối tượng thật là TreeSet, nên cách hiện thực và chi phí đến từ TreeSet.

Nếu chỉ khai báo biến là `Set<Integer>`, đối tượng vẫn là TreeSet và vẫn giữ thứ tự, nhưng các phương thức điều hướng không nằm trên kiểu `Set`. Chọn kiểu biến theo khả năng mà phần mã sử dụng cần biểu đạt, thay vì luôn chọn lớp cụ thể hoặc luôn thu hẹp đến mức mất thông tin cần thiết.

## 3. Quy tắc của cây tìm kiếm nhị phân

Một nút của cây tìm kiếm nhị phân có thể có cây con trái và cây con phải. Với một thứ tự hợp lệ, quy tắc cần đúng cho **toàn bộ cây con**, không chỉ hai nút con ngay cạnh:

```text
mọi giá trị ở cây con trái < giá trị tại nút < mọi giá trị ở cây con phải
```

Dấu `<` ở đây là “đứng trước theo quan hệ so sánh”, không nhất thiết là nhỏ hơn về số học. Nếu dùng thứ tự giảm dần, một số lớn hơn có thể đứng trước một số nhỏ hơn.

Ví dụ minh họa theo thứ tự số nguyên tăng dần:

```text
             40
           /             20      60
        /      /        10   30  50   70
```

Đây là một hình cây minh họa hợp lệ, không phải ảnh chụp nội bộ của một TreeSet sau một chuỗi thao tác cụ thể.

### 3.1. Tìm 30

Bắt đầu ở gốc:

```text
30 so với 40: đứng trước -> sang trái
30 so với 20: đứng sau   -> sang phải
30 so với 30: bằng nhau  -> tìm thấy
```

Không cần xem các nút 50, 60, 70. Quy tắc thứ tự cho phép loại bỏ cả một cây con sau mỗi phép so sánh.

### 3.2. Tìm 35

```text
35 so với 40: sang trái
35 so với 20: sang phải
35 so với 30: sang phải
không có nút ở nhánh tiếp theo -> không tìm thấy
```

Nếu muốn thêm 35, vị trí nhánh trống vừa tìm được là một ứng viên phù hợp theo quy tắc tìm kiếm. Sau khi thêm, cơ chế cân bằng có thể thay đổi hình dạng cây, nhưng phải tiếp tục giữ đúng quan hệ thứ tự.

### 3.3. Giá trị so sánh bằng 0 có vai trò đặc biệt

Với TreeSet, việc gặp kết quả so sánh bằng `0` có nghĩa đã gặp một thành viên tương đương theo thứ tự. `add` không đi tiếp để lưu một nút riêng chỉ vì đối tượng mới khác tham chiếu.

Đó là lý do bộ so sánh vừa điều khiển đường đi trong cây, vừa ảnh hưởng tới tính duy nhất của TreeSet. Bộ so sánh không chỉ được gọi ở thời điểm in dữ liệu.

## 4. Vì sao cây tìm kiếm thông thường chưa đủ?

Cây tìm kiếm nhị phân đúng quy tắc thứ tự vẫn có thể rất cao. Nếu chỉ chèn theo vị trí tìm được mà không điều chỉnh, dãy tăng dần `1, 2, 3, 4, 5, 6, 7` có thể tạo ra:

```text
1
   2
       3
           4
               5
                   6
                       7
```

Tìm phần tử lớn nhất hoặc một giá trị lớn hơn mọi phần tử phải đi gần như qua cả chuỗi. Khi cây có `n` nút, đường đi có thể dài theo `n`, dẫn đến chi phí `O(n)`.

Một hình cân đối hơn với cùng nội dung là:

```text
          4
        /          2     6
      /    /      1   3 5   7
```

Cả hai hình đều có thể cho cùng kết quả duyệt tăng dần:

```text
1, 2, 3, 4, 5, 6, 7
```

Do đó, chỉ kiểm tra dữ liệu in ra đã sắp xếp không chứng minh cây được cân bằng. Thứ tự nội dung và chiều cao cấu trúc là hai thuộc tính khác nhau.

Cây tự cân bằng bổ sung các quy tắc để ngăn đường tìm kiếm suy biến thành một chuỗi dài. TreeSet duy trì điều đó khi thêm và xóa; người gọi không phải xáo trộn dữ liệu đầu vào để “giúp cây cân”.

Cũng không nên hiểu cân bằng là hai cây con của mọi nút luôn có đúng cùng số phần tử, hoặc mọi lá luôn ở cùng độ sâu. Những điều kiện ấy quá chặt và không phải điều TreeSet cần giữ.

## 5. Cây đỏ–đen giữ chiều cao thấp bằng cách nào?

Cây đỏ–đen vẫn là cây tìm kiếm nhị phân. Mỗi nút có thêm thông tin màu để hỗ trợ các bất biến cân bằng.

Một cách mô tả chuẩn gồm:

1. Mỗi nút mang màu đỏ hoặc đen.
2. Gốc là đen.
3. Các lá rỗng quy ước, thường ký hiệu `NIL`, là đen.
4. Nút đỏ không có con đỏ.
5. Từ một nút đến các lá rỗng phía dưới, mọi đường đều có cùng số nút đen theo cùng quy ước đếm.

`NIL` là lá rỗng dùng trong mô hình thuật toán; nó không phải phần tử `null` do người dùng thêm vào Set. Trong triển khai Java, liên kết rỗng có thể được biểu diễn bằng tham chiếu `null`, không cần cấp phát một đối tượng lá riêng cho mọi nhánh.

Thông tin đỏ và đen là metadata của cấu trúc cây. Nó không quyết định thứ tự giá trị và không xuất hiện trong kết quả iterator.

### 5.1. Đường dài không thể dài tùy ý

Do không có hai nút đỏ liên tiếp, giữa các nút đen không thể chen một chuỗi đỏ dài. Mặt khác, mọi đường từ cùng một nút xuống lá rỗng có cùng số nút đen.

Kết hợp hai điều kiện, một đường có thêm nút đỏ vẫn không thể dài gấp tùy ý đường khác. Chiều cao bị khống chế theo logarit của số nút.

Có thể nhìn ý tưởng qua các đường tượng trưng:

```text
đường ngắn hơn:  đen -> đen -> đen -> NIL
đường dài hơn:   đen -> đỏ -> đen -> đỏ -> đen -> NIL
```

Sơ đồ chỉ minh họa ý tưởng chen nút đỏ giữa các mức đen, không khẳng định mọi cây đều có đúng hai đường như thế này.

### 5.2. Một cận chiều cao thường dùng

Với `n >= 1` nút có dữ liệu, cây đỏ–đen có cận:

```text
h <= 2 * log2(n + 1)
```

Ở đây có thể lấy `h` là số cạnh trên đường dài nhất từ gốc tới lá rỗng quy ước. Đổi một quy ước chiều cao khác có thể làm lệch một hằng số nhỏ, nhưng không thay đổi kết luận `O(log n)`.

Ý tưởng chứng minh ngắn:

- Gọi `b` là số nút đen từ sau gốc đến lá rỗng trên mỗi đường.
- Một cây con có chiều cao đen `b` cần ít nhất `2^b - 1` nút có dữ liệu; có thể thấy bằng quy nạp trên hai cây con.
- Vì vậy, `b <= log2(n + 1)`.
- Không có hai nút đỏ liên tiếp nên `h <= 2b`.
- Suy ra cận chiều cao trên.

Điều cần ghi nhớ khi sử dụng collection là: đường tìm kiếm vẫn ngắn theo logarit ngay cả với dữ liệu đầu vào có thứ tự. Không cần dùng công thức để dự đoán chính xác gốc hoặc số phép so sánh của từng lần tìm.

### 5.3. Cân bằng theo chiều cao, không theo hình vẽ đẹp

Một cây đỏ–đen hợp lệ có thể trông lệch về một phía trong hình vẽ. Miễn các bất biến vẫn giữ đúng, chiều cao vẫn nằm trong cận cần thiết.

Nó cũng không phải cây AVL: hai họ cấu trúc dùng tiêu chí cân bằng khác nhau. Khi học TreeSet, nên hiểu chính cơ chế đỏ–đen được TreeMap dùng, thay vì gộp mọi “cây cân bằng” thành một thuật toán giống nhau.

## 6. Phép quay và đổi màu không làm mất thứ tự

Sau thêm hoặc xóa, cây có thể tạm thời vi phạm quy tắc màu. Cơ chế sửa dùng đổi màu và các phép quay cục bộ.

### 6.1. Quay trái

Một phép quay trái có thể minh họa như sau:

```text
Trước quay:                 Sau quay:

      x                          y
     /                         /     A   y                      x   C
       /                     /       B   C                  A   B
```

Trong hình, `A`, `B`, `C` là các cây con, có thể rỗng. Để hình ban đầu là cây tìm kiếm hợp lệ, các giá trị có quan hệ:

```text
A < x < B < y < C
```

Sau quay, duyệt theo thứ tự vẫn cho:

```text
A, x, B, y, C
```

Phép quay đổi quan hệ cha–con và vị trí gốc của vùng nhỏ ấy. Nó không cần sắp xếp lại toàn bộ các phần tử.

### 6.2. Quay phải

Quay phải là thao tác đối xứng:

```text
Trước quay:                 Sau quay:

        y                        x
       /                       /       x   C                    A   y
     /                           /     A   B                        B   C
```

Một phép quay điều chỉnh một số lượng liên kết cố định nên có chi phí cục bộ `O(1)`. Nhưng một thao tác thêm hoặc xóa còn phải tìm vị trí và có thể xử lý các mức tổ tiên. Không được từ “mỗi phép quay là O(1)” suy ra “thêm phần tử là O(1)”.

### 6.3. Đổi màu giải quyết điều gì?

Đổi màu giữ nguyên các liên kết nhưng điều chỉnh cách các mức đen và đỏ phân bố. Tùy tình huống, cơ chế sửa có thể:

- Chỉ cần đổi màu rồi tiếp tục xem xét tổ tiên.
- Quay để đổi hình dạng cục bộ, kết hợp đổi màu.
- Dừng khi các bất biến đã được khôi phục.

Quay đúng quy tắc tìm kiếm chưa đủ để tự bảo đảm mọi quy tắc đỏ–đen. Ngược lại, chỉ đổi màu cũng không giải quyết được mọi trường hợp. Hai công cụ phối hợp trong thuật toán cân bằng.

[Mã nguồn TreeMap của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java) có các phần sửa sau chèn, sửa sau xóa và quay trái/phải. Đây là chi tiết triển khai để kiểm tra cơ chế; ứng dụng dùng TreeSet không gọi trực tiếp các hàm ấy.

## 7. Thêm và xóa liên hệ thế nào với cây cân bằng?

### 7.1. Khi thêm

Có thể hình dung quy trình ở mức ý tưởng:

```text
giá trị mới
    -> so sánh từ gốc, đi trái hoặc phải
    -> nếu gặp so sánh bằng 0: đã có thành viên tương đương
    -> nếu gặp vị trí trống: tạo mục mới
    -> sửa các bất biến màu và hình dạng khi cần
    -> hoàn tất
```

Trong thuật toán đỏ–đen thông dụng, nút mới có thể bắt đầu bằng màu đỏ để không tự tăng số nút đen trên riêng đường mới. Nếu cha cũng đỏ, cần sửa vi phạm đỏ–đỏ; gốc cuối cùng phải đen.

Không phải mọi lần thêm đều gây quay. Một số lần chỉ thêm hợp lệ, một số lần cần đổi màu, một số lần cần quay. Không xây dựng mã ứng dụng dựa trên số phép quay dự kiến cho một dãy đầu vào.

### 7.2. Khi xóa

Đầu tiên cần tìm nút tương ứng theo thứ tự. Việc gỡ liên kết phụ thuộc nút có bao nhiêu con:

- Không có con: xử lý một lá có dữ liệu.
- Có một con: nối lại qua nút con phù hợp.
- Có hai con: có thể dùng phần tử kế tiếp theo thứ tự để chuyển bài toán về trường hợp đơn giản hơn.

Nếu việc xóa làm mất một nút đen trên riêng một đường, thuật toán phải khôi phục điều kiện số nút đen bằng nhau. Quá trình sửa có thể xét nút anh em và tổ tiên, đổi màu hoặc quay.

Nội dung quan trọng khi dùng API là: xóa không chỉ “đặt một ô thành rỗng”, và sau khi xóa, cây vẫn phải giữ điều kiện phục vụ các lần tìm tiếp theo. Chi phí được tính cho cả tìm nút lẫn điều chỉnh cấu trúc.

Không cần ghi nhớ mọi nhánh thuật toán sửa xóa để sử dụng đúng TreeSet. Nếu muốn tự triển khai cây đỏ–đen như bài tập cấu trúc dữ liệu, đó là một nhiệm vụ riêng, cần kiểm thử các bất biến sau từng cập nhật.

### 7.3. Xoay cây không đổi ý nghĩa của Set

Sau cân bằng:

- Những thành viên hiện có vẫn là những thành viên ấy, trừ phần tử vừa thêm hoặc xóa theo yêu cầu.
- Thứ tự duyệt vẫn phù hợp với quan hệ so sánh.
- Gốc và cha–con có thể đã thay đổi.
- Người gọi không nhận được một chỉ số vị trí ổn định cho mỗi phần tử.

Do đó, TreeSet cung cấp thứ tự quan sát được qua API, không cung cấp hợp đồng về hình dạng cây nội bộ.

## 8. Chương trình 1: quan sát các khả năng cơ bản

Lưu tệp `TreeSetBasicsDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class TreeSetBasicsDemo {
    public static void main(String[] args) {
        List<Integer> input = List.of(40, 10, 30, 20, 10, 50);
        NavigableSet<Integer> values = new TreeSet<>();

        for (int value : input) {
            values.add(value);
        }

        System.out.println("input = " + input);
        System.out.println("ascending = " + values);
        System.out.println("add duplicate 20 = " + values.add(20));
        System.out.println("contains 30 = " + values.contains(30));
        System.out.println("remove 30 = " + values.remove(30));
        System.out.println("after remove = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("lower 25 = " + values.lower(25));
        System.out.println("floor 20 = " + values.floor(20));
        System.out.println("ceiling 25 = " + values.ceiling(25));
        System.out.println("higher 40 = " + values.higher(40));
        System.out.println("descending = " + values.descendingSet());
        System.out.println("poll first = " + values.pollFirst());
        System.out.println("poll last = " + values.pollLast());
        System.out.println("remaining = " + values);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 TreeSetBasicsDemo.java
java TreeSetBasicsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
input = [40, 10, 30, 20, 10, 50]
ascending = [10, 20, 30, 40, 50]
add duplicate 20 = false
contains 30 = true
remove 30 = true
after remove = [10, 20, 40, 50]
first = 10
last = 50
lower 25 = 20
floor 20 = 20
ceiling 25 = 40
higher 40 = 50
descending = [50, 40, 20, 10]
poll first = 10
poll last = 50
remaining = [20, 40]
```

Mã dùng ngôn ngữ và API có ở Java 17 trở lên. Các chương trình trong bài được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

### 8.1. Thứ tự đầu vào và thứ tự duyệt

Đầu vào là `40, 10, 30, 20, 10, 50`. Kết quả TreeSet là `10, 20, 30, 40, 50`: tăng dần theo thứ tự tự nhiên của Integer, và chỉ có một giá trị `10`.

Một iterator của TreeSet đi theo thứ tự, không đi theo thứ tự chèn. Kết quả này cũng không có nghĩa các giá trị nằm liên tiếp trong một mảng nội bộ.

### 8.2. Các thao tác tìm và xóa

`contains(30)` và `remove(30)` tìm theo quan hệ so sánh. Sau khi xóa, các phần tử còn lại vẫn được duyệt đúng thứ tự.

Thêm lại `20` trả về `false` vì đã có thành viên tương đương. Đó là sự khác nhau giữa Set với một List cho phép giữ nhiều lần xuất hiện.

### 8.3. Tìm phần tử lân cận

Sau khi xóa 30, nội dung là `[10, 20, 40, 50]`:

| Lời gọi | Điều kiện tìm | Kết quả |
|---|---|---|
| `lower(25)` | Lớn nhất nhưng đứng trước 25 | 20 |
| `floor(20)` | Lớn nhất nhưng không đứng sau 20 | 20 |
| `ceiling(25)` | Nhỏ nhất nhưng không đứng trước 25 | 40 |
| `higher(40)` | Nhỏ nhất nhưng đứng sau 40 | 50 |

Cách nói “trước” và “sau” giúp nhớ rằng các khái niệm này phụ thuộc thứ tự của Set. Với bộ so sánh đảo chiều, không nên suy luận bằng trục số tăng dần rồi bỏ qua comparator.

Những khả năng này liên hệ trực tiếp với cấu trúc cây có thứ tự: trong lúc tìm, chương trình có thể ghi nhận ứng viên biên phù hợp và tiếp tục đi vào cây con cần thiết.

### 8.4. Hai đầu và góc nhìn đảo chiều

`first` và `last` xem hai đầu theo thứ tự. `pollFirst` và `pollLast` vừa lấy vừa gỡ phần tử ở đầu tương ứng.

Trong ví dụ, `descendingSet()` cho một góc nhìn theo thứ tự đảo ngược, không phải yêu cầu sắp xếp rồi sao chép toàn bộ dữ liệu thành một TreeSet độc lập. Việc cập nhật qua các góc nhìn có liên hệ với tập gốc; không coi đó là bản chụp tách biệt.

Với Set rỗng, `first` và `last` ném `NoSuchElementException`; các phép thăm dò lân cận hoặc `pollFirst`/`pollLast` trả về `null` khi không có kết quả. Hãy chọn API theo việc thiếu dữ liệu là tình huống bình thường hay một vi phạm giả định của luồng xử lý.

## 9. Chi phí: phải biết đang đếm điều gì

Gọi `n` là số thành viên hiện có trong một TreeSet đầy đủ, và trước hết giả sử một lần so sánh có chi phí hằng số.

| Thao tác hoặc quá trình | Chi phí cần hiểu | Cơ sở |
|---|---|---|
| `contains` | `O(log n)` | Đi theo một đường tìm kiếm của cây cân bằng |
| `add` | `O(log n)` | Tìm vị trí và duy trì cân bằng |
| `remove` | `O(log n)` | Tìm mục và duy trì cân bằng khi xóa |
| `size` trên TreeSet đầy đủ | `O(1)` trong triển khai TreeMap | Có số lượng thành viên được duy trì |
| Duyệt toàn bộ một lần | `O(n)` về số nút được thăm | Lần lượt đi qua các thành viên theo thứ tự |
| Thêm n giá trị bằng các lời gọi add thông thường | Cận tổng `O(n log n)` | Cộng chi phí cập nhật tăng dần quy mô |
| Bộ nhớ lưu n thành viên | `O(n)` cho cấu trúc lưu trữ | Cần các mục và liên kết cây |

Bảng không khẳng định rằng mọi phương thức của mọi góc nhìn con đều có chi phí giống hệt TreeSet đầy đủ. Ví dụ, không lấy phân tích `size` của cấu trúc gốc để suy ra tự động chi phí `size` của mọi khoảng nhìn.

### 9.1. O(log n) là cận tăng trưởng, không phải một số bước chính xác

Một lần tìm có thể thấy ngay giá trị ở gốc và chỉ cần rất ít so sánh. Lần khác phải đi gần tới lá. Cận logarit mô tả quy mô đường tìm khi `n` tăng, không yêu cầu mọi lời gọi có đúng `log2(n)` phép so sánh.

Cân bằng đỏ–đen cũng không phải tìm kiếm nhị phân trên mảng: cây có các liên kết và hình dạng động; mảng đã sắp xếp dùng truy cập theo chỉ số để chọn điểm giữa. Hai cách đều có đường tìm logarit nhưng chi phí cập nhật và cách bố trí bộ nhớ khác nhau.

### 9.2. Phải cộng chi phí của comparator

Nếu một lần so sánh tốn `C`, phần tìm kiếm có thể được mô tả theo dạng:

```text
O(C * log n)
```

Với so sánh số nguyên đơn giản, coi `C` là hằng số thường phù hợp. Với chuỗi dài, nhiều tiêu chí, tính toán suy ra phức tạp hoặc dữ liệu ngoài bộ nhớ, chi phí mỗi lần so sánh có thể đáng kể.

Không đặt tác vụ chậm hoặc có tác dụng phụ như truy vấn dịch vụ, ghi dữ liệu hay thay đổi phần tử vào comparator. Comparator cần biểu đạt quan hệ thứ tự ổn định; TreeSet có thể gọi nó nhiều lần trong các thao tác khác nhau.

### 9.3. Bộ nhớ và tính cục bộ

Một cây dùng các mục và liên kết thay vì chỉ một dãy tham chiếu liên tiếp. Điều này có chi phí bộ nhớ và việc đi theo liên kết. Không thể chỉ nhìn `O(log n)` rồi kết luận TreeSet luôn chạy nhanh hơn mọi cấu trúc khác.

Nếu dữ liệu được xây một lần rồi đọc rất nhiều, một List sắp xếp có thể là lựa chọn đáng cân nhắc. Nếu chủ yếu kiểm tra thành viên mà không cần thứ tự, cấu trúc băm có thể phù hợp hơn. TreeSet đáng giá khi thứ tự và cập nhật động cùng phục vụ yêu cầu thực tế.

Không nêu một số byte cố định cho mỗi phần tử nếu chưa xác định JVM, chế độ tham chiếu và cách đo. Phân tích `O(n)` cho bộ nhớ không thay thế việc đo dung lượng trong môi trường cụ thể.

## 10. Chương trình 2: dữ liệu tăng dần không làm cây biến thành chuỗi

Chương trình dưới đây thêm các số theo đúng thứ tự tăng dần, rồi tìm một số lớn hơn tất cả số đã thêm. Comparator đếm số lần so sánh, nhưng vẫn luôn trả về kết quả của `Integer.compare`.

Lưu tệp `TreeSetSearchCostDemo.java`:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class TreeSetSearchCostDemo {
    static final class CountingComparator implements Comparator<Integer> {
        private int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }

        int calls() {
            return calls;
        }
    }

    static int ceilLog2(int value) {
        if (value <= 1) {
            return 0;
        }
        return 32 - Integer.numberOfLeadingZeros(value - 1);
    }

    public static void main(String[] args) {
        for (int n : new int[] {31, 127, 511, 2047}) {
            CountingComparator order = new CountingComparator();
            TreeSet<Integer> values = new TreeSet<>(order);

            for (int value = 0; value < n; value++) {
                values.add(value);
            }

            order.reset();
            boolean found = values.contains(n);
            int comparisons = order.calls();
            int conservativeBound = 2 * ceilLog2(n + 1);

            System.out.println("n=" + n
                    + ", found=" + found
                    + ", comparisons=" + comparisons
                    + ", bound=" + conservativeBound
                    + ", withinBound=" + (comparisons <= conservativeBound));
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 TreeSetSearchCostDemo.java
java TreeSetSearchCostDemo
```

Kết quả của lần chạy kiểm chứng:

```text
n=31, found=false, comparisons=8, bound=10, withinBound=true
n=127, found=false, comparisons=12, bound=14, withinBound=true
n=511, found=false, comparisons=16, bound=18, withinBound=true
n=2047, found=false, comparisons=20, bound=22, withinBound=true
```

Bộ đếm được đặt lại **sau khi xây Set**, nên các con số chỉ thuộc về một lần `contains(n)`, không bao gồm quá trình thêm dữ liệu.

### 10.1. Đọc kết quả đúng mức

Trong lần chạy này, số phần tử tăng từ 31 lên 2047, còn số so sánh của phép tìm đang đo tăng từ 8 lên 20. Nếu là cây tìm kiếm ngây thơ suy biến sau chèn tăng dần, đường tìm một số lớn hơn tất cả phần tử có thể đi qua toàn bộ chuỗi.

Cột `bound` là `2 * ceil(log2(n + 1))`, một cận bảo thủ dựa trên ý tưởng chiều cao đỏ–đen. Với các kích thước trong chương trình, `n + 1` là lũy thừa của 2 nên phép làm tròn không gây khó đọc.

Bộ đếm này không đo nano giây và không chứng minh TreeSet nhanh hơn một collection khác. Nó chỉ quan sát số lần comparator được gọi ở một kịch bản cụ thể.

### 10.2. Không đóng đinh con số vào hợp đồng API

Các giá trị 8, 12, 16, 20 là output đã kiểm chứng của môi trường chạy trong bài. Hình dạng cây, đường đi cụ thể và số lần gọi comparator có thể phụ thuộc lịch sử cập nhật hoặc triển khai.

Khi kiểm thử ứng dụng, không viết yêu cầu “TreeSet có 511 phần tử thì contains phải gọi comparator đúng 16 lần”. Yêu cầu đáng bảo vệ là kết quả thành viên đúng, thứ tự đúng, và lựa chọn cấu trúc phù hợp với bảo đảm của nó.

Một số phép đo hữu hạn cũng không phải chứng minh toán học cho `O(log n)`. Cơ sở tổng quát đến từ bất biến cân bằng và phân tích chiều cao; chương trình giúp nối lý thuyết với một quan sát có thể tái hiện.

### 10.3. Vì sao bộ đếm không phá thứ tự?

Comparator này có một trường đếm thay đổi, nhưng trường ấy không tham gia quyết định kết quả so sánh. Với cùng hai giá trị, kết quả thứ tự vẫn giữ nguyên.

Điều này khác với một comparator dùng số lần gọi để luân phiên trả về lớn hơn hoặc nhỏ hơn. Comparator như vậy không biểu đạt một thứ tự ổn định và không thể dùng làm nền tảng hợp lệ cho cây tìm kiếm.

## 11. Bộ so sánh là một phần của cấu trúc, không phải tùy chọn trang trí

TreeSet có hai cách phổ biến để xác định thứ tự:

```java
// Trích đoạn minh họa; cần import các kiểu java.util tương ứng.
TreeSet<Integer> natural = new TreeSet<>();

TreeSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
```

Ở trường hợp đầu, phần tử cần hỗ trợ thứ tự tự nhiên phù hợp, thường qua `Comparable`. Ở trường hợp sau, comparator đã cung cấp quy tắc.

Trong cả hai trường hợp, cùng quy tắc phải được dùng nhất quán cho mọi lần đi trái, đi phải hoặc kết luận tương đương.

Theo [hợp đồng Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T)), dấu kết quả phải đảo đúng khi đổi vị trí hai đối số, quan hệ phải có tính bắc cầu, và hai giá trị so sánh bằng 0 phải có quan hệ thứ tự nhất quán đối với giá trị thứ ba.

Nếu một comparator tạo chu trình kiểu `A < B`, `B < C` nhưng `C < A`, việc loại bỏ cả cây con sau một phép so sánh không còn có cơ sở. Cây có thể vẫn có hình dạng thấp nhưng không cung cấp ngữ nghĩa tìm kiếm đúng theo một thứ tự hợp lệ.

Đây là hai trục cần giữ riêng:

```text
cân bằng hình dạng -> đường đi ngắn
thứ tự hợp lệ     -> đường đi có ý nghĩa
```

Một cây cân bằng không thể sửa một comparator sai.

### 11.1. So sánh bằng 0 và equals

Đối với TreeSet, `compare(a, b) == 0` hoặc `a.compareTo(b) == 0` xác định hai phần tử tương đương để lưu thành viên.

Muốn tuân thủ hợp đồng Set nói chung, quan hệ tương đương đó cần phù hợp với `equals`. Nếu không phù hợp, hành vi theo thứ tự của TreeSet vẫn có thể rõ ràng, nhưng cách hiểu “duy nhất theo equals” của Set không còn được đáp ứng.

Vì vậy, nếu thêm một đối tượng mới mà `add` trả về `false`, cần hỏi comparator có xem nó bằng một thành viên đã có hay không. Không chỉ kiểm tra `equals` rồi kết luận cây làm mất dữ liệu.

### 11.2. Không so sánh int bằng phép trừ tùy tiện

Một cách dễ sai là:

```java
// Không dùng để so sánh int tổng quát: hiệu có thể tràn.
(left, right) -> left - right
```

Hãy dùng:

```java
// Trích đoạn: so sánh int không dựa vào hiệu có thể tràn.
Integer::compare
```

Hoặc dùng các hàm như `Comparator.comparingInt` khi so sánh một thuộc tính. Quan hệ thứ tự là nền tảng tìm kiếm, nên lỗi tràn trong comparator không chỉ làm thứ tự in ra hơi khác; nó có thể phá giả định đi nhánh.

## 12. Chương trình 3: thứ tự quyết định thành viên nào được giữ

Lưu tệp `TreeSetComparisonDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class TreeSetComparisonDemo {
    record Entry(int priority, String name) {
    }

    public static void main(String[] args) {
        TreeSet<String> words = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

        System.out.println("add java = " + words.add("java"));
        System.out.println("add JAVA = " + words.add("JAVA"));
        System.out.println("String equals = " + "java".equals("JAVA"));
        System.out.println("contains JaVa = " + words.contains("JaVa"));
        System.out.println("case-insensitive members = " + words);

        TreeSet<String> natural = new TreeSet<>(List.of("java", "JAVA"));
        System.out.println("natural members = " + natural);

        Comparator<Entry> byPriorityThenName =
                Comparator.comparingInt(Entry::priority)
                        .thenComparing(Entry::name);
        TreeSet<Entry> entries = new TreeSet<>(byPriorityThenName);
        entries.add(new Entry(2, "B"));
        entries.add(new Entry(1, "A"));
        entries.add(new Entry(2, "A"));

        System.out.println("entry count = " + entries.size());
        for (Entry entry : entries) {
            System.out.println("entry = "
                    + entry.priority() + ":" + entry.name());
        }
        System.out.println("add equal entry = "
                + entries.add(new Entry(2, "A")));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 TreeSetComparisonDemo.java
java TreeSetComparisonDemo
```

Kết quả của lần chạy kiểm chứng:

```text
add java = true
add JAVA = false
String equals = false
contains JaVa = true
case-insensitive members = [java]
natural members = [JAVA, java]
entry count = 3
entry = 1:A
entry = 2:A
entry = 2:B
add equal entry = false
```

### 12.1. Chuỗi không phân biệt hoa–thường

Comparator `String.CASE_INSENSITIVE_ORDER` xem `"java"` và `"JAVA"` tương đương trong so sánh. Vì thế:

- `add("java")` lần đầu thành công.
- `add("JAVA")` trả về `false`.
- `contains("JaVa")` trả về `true`.
- Chuỗi ban đầu `"java"` vẫn là đại diện đang được giữ.

Trong khi đó, `String.equals` phân biệt hoa–thường. Ví dụ này cố ý cho thấy sự không nhất quán giữa quan hệ thứ tự và equals; không nên che điều đó khi thiết kế API nhận một Set.

TreeSet theo thứ tự tự nhiên giữ cả `"JAVA"` và `"java"` vì thứ tự tự nhiên của String phân biệt hai giá trị ấy.

### 12.2. Tiêu chí phụ giúp biểu đạt đúng sự khác nhau

Record `Entry` có hai thành phần `priority` và `name`. Comparator xét độ ưu tiên trước, sau đó xét tên. Vì vậy, `Entry(2, "A")` và `Entry(2, "B")` không bị gộp.

Với các tên khác `null` trong ví dụ, so sánh bằng 0 khi cả hai thành phần bằng nhau, phù hợp với quy tắc bằng nhau của record.

Nếu chỉ dùng:

```java
// Trích đoạn: chỉ phù hợp nếu mỗi priority chỉ được giữ một đại diện.
Comparator<Entry> onlyPriority =
        Comparator.comparingInt(Entry::priority);
```

thì hai Entry cùng độ ưu tiên sẽ tương đương theo TreeSet, dù tên khác nhau. Đây không phải vấn đề cây chưa đủ cân bằng; đó là quan hệ thành viên đã được lập trình.

Không thêm tiêu chí phụ một cách máy móc chỉ để “không mất phần tử”. Phải chọn tiêu chí phản ánh đúng sự khác nhau mà mô hình muốn giữ. Nếu cần nhiều lần xuất hiện của cùng một giá trị theo đúng mọi thành phần, Set vốn không phải cấu trúc biểu đạt số lần xuất hiện.

## 13. Duy trì thứ tự khi dữ liệu thay đổi

TreeSet chỉ có thể tổ chức đúng khi dữ liệu dùng so sánh ổn định trong thời gian phần tử nằm trong cây.

Giả sử đối tượng công việc được đặt trong cây theo `priority`. Sau khi thêm, mã gọi sửa `priority` qua một setter. Đối tượng vẫn ở vị trí được chọn theo giá trị cũ, trong khi các lần tìm tiếp theo dùng giá trị mới.

Cân bằng đỏ–đen không tự theo dõi setter. Các quy tắc màu có thể vẫn đúng về hình dạng, nhưng quy tắc thứ tự giá trị đã sai. Những hậu quả có thể gồm duyệt không còn đúng thứ tự mong đợi, tra cứu không thấy hoặc xóa không đúng kỳ vọng.

Một hướng thiết kế tốt là:

- Dùng giá trị bất biến làm phần tử khi toàn bộ giá trị xác định thứ tự.
- Hoặc giữ ổn định các thuộc tính dùng so sánh, chỉ cho đổi dữ liệu không ảnh hưởng quan hệ thứ tự.
- Nếu phải đổi thuộc tính so sánh, gỡ khi giá trị cũ còn hợp lệ rồi thêm giá trị mới theo một quy trình có kiểm soát.
- Khi có thể, tạo đối tượng mới thay vì sửa cùng một khóa đang được nhiều nơi giữ.

Comparator cũng không nên dựa vào một cấu hình ngoài có thể bị đổi tùy ý sau khi cây đã có dữ liệu. Ví dụ, đảo cờ “tăng dần/giảm dần” trong comparator đang được dùng không tự xây lại cây.

Đổi comparator có ý nghĩa như đổi quy tắc tổ chức. Hãy tạo một cấu trúc mới với quy tắc mới và nạp dữ liệu hợp lệ theo yêu cầu, thay vì giả định cây cũ sẽ tự đảo liên kết sau khi một biến ngoài thay đổi.

Không dùng ngoại lệ fail-fast như một cơ chế phát hiện mọi lỗi này. Việc sửa trường của một phần tử không đồng nghĩa với một thao tác cấu trúc được thực hiện qua TreeSet.

## 14. Một số giới hạn cần biết khi áp dụng

### 14.1. null phụ thuộc quy tắc so sánh

TreeSet theo thứ tự tự nhiên không chấp nhận `null`. Với comparator được cung cấp rõ ràng và hỗ trợ `null`, có thể thiết kế một thứ tự cho giá trị này, chẳng hạn thông qua `Comparator.nullsFirst`.

Điều quan trọng là phần tử phải được so sánh hợp lệ theo cùng một quy tắc. Không suy luận rằng “mọi Set đều nhận null” hoặc “mọi TreeSet tuyệt đối không thể nhận null”.

Nếu cho phép `null`, các phương thức trả về `null` khi không tìm được còn cần được đọc cẩn thận theo ngữ cảnh. Chọn cấm `null` thường làm rõ hơn mô hình dữ liệu nếu nghiệp vụ không cần giá trị thiếu ấy.

### 14.2. Phần tử phải so sánh được với nhau

Có kiểu generic `TreeSet<MyType>` chưa có nghĩa MyType tự nhiên đã có thứ tự. Cần MyType có quy tắc Comparable phù hợp hoặc cung cấp Comparator.

Một lỗi so sánh có thể xuất hiện ngay lúc thêm, kể cả không nên chờ tới khi đã có nhiều phần tử mới kiểm tra. Khả năng biên dịch và khả năng tạo quan hệ thứ tự hợp lệ là hai việc khác nhau.

### 14.3. Các góc nhìn theo khoảng không phải bản sao

Các phương thức như `subSet`, `headSet`, `tailSet` cho phép làm việc với một vùng theo thứ tự. Đây là các góc nhìn có ràng buộc biên và liên hệ với tập gốc.

Điều này hữu ích khi bài toán cần một khoảng giá trị, vì thứ tự đã có sẵn để định vị các biên. Nhưng không coi việc tạo góc nhìn là đã tách dữ liệu sang một bản chụp độc lập.

Thêm ngoài biên qua một góc nhìn bị giới hạn có thể bị từ chối. Khi cần bản sao riêng, tạo một collection mới với thứ tự và chính sách dữ liệu phù hợp.

### 14.4. Không có truy cập theo thứ hạng

`first()` lấy giá trị đầu theo thứ tự; nó không phải `get(0)` của một danh sách có chỉ số. TreeSet không trực tiếp cung cấp “phần tử thứ 1000” với chi phí logarit qua API chuẩn.

Nếu bài toán thường xuyên truy cập theo vị trí trong dãy đã sắp xếp, cần xem lại cấu trúc phù hợp. Không nên lặp từ đầu nhiều lần rồi cho rằng mỗi lần là `O(log n)` chỉ vì dữ liệu nằm trong cây cân bằng.

### 14.5. Không tự đồng bộ giữa nhiều luồng

TreeSet thông thường không tự cung cấp khả năng đồng bộ cho nhiều luồng cập nhật. Việc cây tự cân bằng là tính chất của thuật toán tổ chức, không phải cam kết an toàn khi dùng đồng thời.

Khi có nhiều luồng, hãy chọn cơ chế phối hợp hoặc một cấu trúc đồng thời phù hợp với yêu cầu. Dù chọn cách nào, comparator và dữ liệu dùng so sánh vẫn phải có ngữ nghĩa ổn định.

## 15. Chọn TreeSet khi thứ tự phục vụ thao tác thật

TreeSet phù hợp với các nhu cầu như:

- Kiểm tra thành viên đồng thời thường xuyên thêm và xóa.
- Duyệt các giá trị duy nhất theo cùng một thứ tự ổn định.
- Tìm mốc trước hoặc sau một giá trị.
- Làm việc với các khoảng của một miền có thứ tự.
- Lấy hoặc gỡ phần tử ở một đầu theo thứ tự.

Một vài câu hỏi giúp chọn cấu trúc:

| Nhu cầu chủ đạo | Điều cần cân nhắc |
|---|---|
| Chỉ kiểm tra đã có, không cần thứ tự | Có thể không cần trả chi phí duy trì cây có thứ tự |
| Giữ đúng thứ tự chèn | Đây không phải thứ tự TreeSet biểu đạt |
| Giữ mọi lần xuất hiện của giá trị | Cần mô hình cho phép trùng hoặc đếm số lần |
| Sắp xếp một lần rồi đọc theo chỉ số | Một danh sách sắp xếp có thể phù hợp hơn |
| Thường xuyên cập nhật và tìm lân cận theo thứ tự | Đây là lợi thế trực tiếp của cấu trúc cây có thứ tự |

Không chọn TreeSet chỉ vì chữ “Tree” hoặc vì nghe nói cây luôn nhanh. Lợi ích đến từ việc một cấu trúc duy trì đồng thời tính duy nhất, thứ tự và đường tìm kiếm thấp.

Cũng không bắt TreeSet làm nhiệm vụ của một Map. Nếu mỗi khóa có một giá trị cần cập nhật độc lập, TreeMap có thể thể hiện yêu cầu rõ hơn. TreeSet quản lý thành viên; thêm một phần tử tương đương không phải thao tác ghi đè một bản ghi dữ liệu.

## 16. Kiểm chứng đúng thứ tự, đúng thành viên và đúng giả định

Khi viết kiểm tra cho mã sử dụng TreeSet, nên bảo vệ hành vi quan sát được mà ứng dụng cần:

1. Dữ liệu duyệt ra đúng quan hệ thứ tự đã chọn.
2. Hai phần tử tương đương theo quy tắc mong muốn không tạo thêm thành viên.
3. Hai phần tử khác nhau mà nghiệp vụ muốn giữ đều còn tồn tại.
4. `contains`, `remove` và các phép tìm biên xử lý đúng dữ liệu đại diện.
5. Thuộc tính được phép cập nhật không phá quy tắc so sánh.
6. Comparator xử lý đúng các giá trị biên, tránh lỗi tràn và bảo đảm tính bắc cầu.

Có thể đối chiếu dãy duyệt với một danh sách kỳ vọng trong những ví dụ nhỏ có thứ tự xác định. Khác với một Set không bảo đảm thứ tự, ở đây thứ tự là một phần của yêu cầu.

Nhưng không kiểm tra gốc phải là một giá trị cụ thể, nút nào phải đỏ, hay một lần tìm phải dùng đúng số phép so sánh của máy đang chạy, nếu ứng dụng không tự triển khai cây. Những điều đó thuộc hình dạng nội bộ, không phải hợp đồng TreeSet cung cấp.

Nếu đang tự viết cây đỏ–đen để học thuật toán, phạm vi kiểm tra khác đi: sau mỗi cập nhật cần kiểm tra cả quy tắc cây tìm kiếm, quan hệ cha–con, màu gốc, không đỏ–đỏ, chiều cao đen và số lượng nút. Đừng lấy vài output sắp xếp đúng làm bằng chứng đầy đủ cho một cây tự triển khai.

## 17. Bài tập áp dụng

### Bài 1: đầu vào đã tăng dần

Thêm các số từ 1 đến n vào TreeSet. Có cần xáo trộn trước để tránh cây suy biến không?

**Gợi ý trả lời:** không. TreeSet dựa trên cơ chế tự cân bằng. Xáo trộn đầu vào không phải điều kiện để các thao tác cơ bản giữ cận logarit.

### Bài 2: output giống nhau, cấu trúc khác nhau

Hai cây cùng duyệt ra `1, 2, 3, 4, 5, 6, 7`. Một cây là chuỗi, một cây có chiều cao thấp.

Có thể kết luận chi phí tìm kiếm giống nhau chỉ từ output không?

**Gợi ý trả lời:** không. Output thể hiện thứ tự nội dung, còn chi phí đường tìm phụ thuộc chiều cao và cấu trúc.

### Bài 3: quay trái có đổi thứ tự không?

Dùng sơ đồ `A, x, B, y, C` trong phần phép quay để giải thích vì sao thứ tự duyệt không đổi.

**Gợi ý trả lời:** phép quay giữ các quan hệ `A < x < B < y < C`. Nó đổi liên kết cục bộ, không đổi chuỗi duyệt theo thứ tự.

### Bài 4: chỉ so theo độ dài chuỗi

TreeSet dùng `Comparator.comparingInt(String::length)`. Thêm `"cat"` và `"dog"`.

Có giữ cả hai không, và đây có phải lỗi cân bằng không?

**Gợi ý trả lời:** hai chuỗi có cùng độ dài nên comparator trả về 0; TreeSet chỉ giữ một đại diện. Đây là hệ quả quy tắc tương đương, không phải lỗi hình dạng cây. Nếu muốn giữ cả hai, cần một quan hệ phân biệt phù hợp với nghiệp vụ.

### Bài 5: khóa so sánh bị sửa

Một công việc nằm trong TreeSet theo mức ưu tiên, rồi mức ưu tiên bị sửa trực tiếp.

Cân bằng đỏ–đen có tự chuyển công việc sang vị trí mới không?

**Gợi ý trả lời:** không. Cấu trúc không tự theo dõi setter. Cần khóa ổn định hoặc một luồng gỡ trước, thay đổi rồi thêm lại được quản lý đúng.

### Bài 6: một lần so sánh rất chậm

Comparator phải xử lý một chuỗi dài hoặc tính một thuộc tính tốn kém. Có thể chỉ nhìn `O(log n)` rồi coi thời gian tìm là nhỏ không?

**Gợi ý trả lời:** không. Cần tính cả chi phí mỗi lần so sánh. Số phép so sánh logarit không làm một comparator tốn kém trở thành miễn phí.

### Bài 7: tìm phần tử thứ k

Yêu cầu lấy thường xuyên phần tử thứ k trong dãy theo thứ tự. TreeSet có sẵn `get(k)` với `O(log n)` không?

**Gợi ý trả lời:** không. API chuẩn không cung cấp truy cập theo thứ hạng như vậy. Cần chọn cấu trúc theo đúng thao tác mà bài toán sử dụng.

Khi đánh giá một ứng dụng dùng TreeSet, hãy chỉ rõ quan hệ thứ tự nào đang dẫn đường, các thành viên nào phải được coi là tương đương, và vì sao dữ liệu dùng so sánh giữ ổn định trong suốt thời gian nằm trong cây.
