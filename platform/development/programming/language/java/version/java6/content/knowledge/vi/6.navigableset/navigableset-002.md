# lower, floor, ceiling và higher trong NavigableSet

## 1. Bài toán: tìm phần tử sát một mốc

Giả sử các mức giá đang có là `10, 20, 30, 40`. Người dùng đưa vào một mốc x. Ta có thể cần:

- Mức ngay trước x, không chấp nhận bằng x.
- Mức lớn nhất vẫn không vượt x.
- Mức nhỏ nhất đạt ít nhất x.
- Mức ngay sau x, không chấp nhận bằng x.

`Set` thông thường trả lời tốt câu hỏi “có phần tử này không?”. `NavigableSet<E>` còn mô tả quan hệ thứ tự để trả lời các câu hỏi ở sát một mốc bằng `lower`, `floor`, `ceiling` và `higher`. `TreeSet<E>` là cách cài đặt thường dùng khi cần vừa giữ các giá trị duy nhất vừa truy vấn theo thứ tự.

Điều quan trọng là tách hai quyết định: **tìm ở phía nào của x** và **có chấp nhận phần tử bằng x không**.

## 2. Bốn hợp đồng và cách ghi nhớ

Trong phần này, giả sử tập dùng thứ tự tự nhiên tăng dần. Với kết quả y:

| Phương thức | Điều kiện | Phần tử được chọn |
| --- | --- | --- |
| `lower(x)` | `y < x` | Lớn nhất trong các phần tử nhỏ hơn x |
| `floor(x)` | `y <= x` | Lớn nhất trong các phần tử không vượt x |
| `ceiling(x)` | `y >= x` | Nhỏ nhất trong các phần tử không nhỏ hơn x |
| `higher(x)` | `y > x` | Nhỏ nhất trong các phần tử lớn hơn x |

Cả bốn trả về **phần tử kiểu E**, hoặc `null` nếu không có phần tử thỏa mãn. Chúng không trả về chỉ số và không yêu cầu x phải nằm trong tập. Đây là hợp đồng hiện hành của [NavigableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableSet.html).

Cách nhớ:

- `lower` và `higher` là hai phía **nghiêm ngặt**, bỏ qua phần tử bằng mốc.
- `floor` và `ceiling` **cho phép bằng**.
- “Sàn” chọn từ phía dưới; “trần” chọn từ phía trên, theo thứ tự mà tập đang dùng.

Các tên này không phải phép làm tròn số thực của `Math.floor` hoặc `Math.ceil`. Tập có thể chứa số nguyên, chuỗi, ngày giờ hoặc đối tượng nghiệp vụ; kết quả luôn phải là một phần tử thực sự đang có trong tập.

### 2.1. Khi x có trong tập

Với `[10, 20, 30, 40]` và `x = 20`:

```text
lower(20)   -> 10
floor(20)   -> 20
ceiling(20) -> 20
higher(20)  -> 30
```

Hai phương thức ở giữa chấp nhận 20. Hai phương thức còn lại phải vượt qua 20 để tìm hàng xóm đúng phía.

### 2.2. Khi x nằm giữa hai phần tử

Với cùng tập và `x = 25`:

```text
lower(25)   -> 20
floor(25)   -> 20
ceiling(25) -> 30
higher(25)  -> 30
```

Vì không có phần tử bằng 25, việc “cho phép bằng” không tạo ra khác biệt. Điều này thường làm người học tưởng hai cặp phương thức giống nhau; thử thêm mốc có trong tập sẽ thấy khác biệt ngay.

### 2.3. Khi x nằm ngoài miền dữ liệu

| x | lower(x) | floor(x) | ceiling(x) | higher(x) |
| --- | --- | --- | --- | --- |
| 5 | null | null | 10 | 10 |
| 10 | null | 10 | 10 | 20 |
| 40 | 30 | 40 | 40 | null |
| 45 | 40 | 40 | null | null |

Không có phần tử phù hợp là một kết quả bình thường, không phải lỗi của cấu trúc dữ liệu. Với tập rỗng và một mốc hợp lệ, cả bốn kết quả đều là `null`.

## 3. “Nhỏ hơn” và “bằng” do thứ tự của tập quyết định

### 3.1. Thứ tự tự nhiên hoặc Comparator

`NavigableSet` không nhất thiết sắp xếp theo giá trị số tăng dần. Nó dùng thứ tự tự nhiên của phần tử hoặc `Comparator` được cấu hình.

Nếu gọi hàm so sánh của tập là c, hợp đồng tổng quát là:

| Phương thức | Điều kiện với ứng viên y và mốc x |
| --- | --- |
| `lower(x)` | `c.compare(y, x) < 0`, chọn phần tử cuối cùng trước x |
| `floor(x)` | `c.compare(y, x) <= 0`, chọn phần tử cuối cùng không sau x |
| `ceiling(x)` | `c.compare(y, x) >= 0`, chọn phần tử đầu tiên không trước x |
| `higher(x)` | `c.compare(y, x) > 0`, chọn phần tử đầu tiên sau x |

“Đầu tiên” và “cuối cùng” ở đây đều theo thứ tự của tập. Với số nguyên tăng dần, nó trùng với trực giác nhỏ/lớn về giá trị; với thứ tự đảo hoặc khóa nhiều trường, phải đọc lại điều kiện so sánh.

Không cài comparator bằng phép trừ như `a - b` cho số nguyên có thể lớn: phép trừ có thể tràn và làm sai thứ tự. Dùng `Integer.compare`, `Long.compare`, `Comparator.comparingInt` hoặc `comparingLong` tùy dữ liệu.

### 3.2. descendingSet đảo cả ý nghĩa điều hướng

Với tập tăng `[10, 20, 30, 40]`, góc nhìn giảm dần là `[40, 30, 20, 10]`.

Trên góc nhìn này:

```text
descending.lower(20)   -> 30
descending.floor(20)   -> 20
descending.ceiling(20) -> 20
descending.higher(20)  -> 10
```

Theo thứ tự giảm, 30 đứng trước 20, còn 10 đứng sau 20. Vì thế `lower` không còn đồng nghĩa với “số nhỏ hơn”.

Các quan hệ đối chiếu hữu ích với `s` là tập gốc và `d = s.descendingSet()`:

```text
d.lower(x)   tương ứng s.higher(x)
d.floor(x)   tương ứng s.ceiling(x)
d.ceiling(x) tương ứng s.floor(x)
d.higher(x)  tương ứng s.lower(x)
```

`descendingSet()` là một góc nhìn liên kết với tập gốc. Việc chỉ gọi các truy vấn trên nó không đảo lại hoặc sửa dữ liệu trong tập gốc. Nếu thêm/xóa qua một góc nhìn có hỗ trợ thay đổi, tập gốc cũng bị ảnh hưởng.

### 3.3. Bằng theo comparator không nhất thiết là equals

Giả sử đối tượng giá có hai trường `amount` và `label`, nhưng comparator chỉ xét `amount`. Hai đối tượng `Price(200, "standard")` và `Price(200, "lookup")` so sánh bằng nhau theo comparator.

Khi tập đang giữ đối tượng thứ nhất:

- `floor(lookup)` và `ceiling(lookup)` trả lại **đối tượng đang lưu** có giá 200.
- `lower(lookup)` bỏ qua toàn bộ vị trí so sánh bằng 200.
- `higher(lookup)` cũng phải đi sang vị trí khác 200.
- Thêm một đối tượng khác cùng amount có thể trả `false`, dù nhãn khác.

Ví dụ hoàn chỉnh bên dưới cố ý minh họa điểm này. `record Price` mặc định so sánh `equals` bằng cả hai trường, nên comparator chỉ theo amount không nhất quán với `equals`. Hành vi điều hướng vẫn xác định, nhưng thiết kế như vậy không tuân thủ đầy đủ hợp đồng chung của `Set`.

Trong dữ liệu thực tế, nên chọn mô hình nhất quán: nếu phần tử chính là mức giá, dùng `NavigableSet<Long>`; nếu mỗi mức giá có dữ liệu đi kèm, cân nhắc `NavigableMap<Long, Price>`; nếu nhiều đối tượng cùng giá đều phải tồn tại trong tập, cần một khóa phân biệt bổ sung. Khi thêm trường phân biệt vào comparator, ranh giới tìm kiếm là ranh giới của **toàn bộ khóa**, không còn chỉ là giá. Đặc điểm về thứ tự, tính duy nhất và `equals` được mô tả trong [TreeSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Đừng sửa trực tiếp trường tham gia sắp xếp của một phần tử đang nằm trong `TreeSet`. Tập không tự định vị lại phần tử sau khi trường đổi, khiến cả tìm kiếm và truy vấn hàng xóm có thể sai. Dùng khóa bất biến hoặc xóa phần tử bằng trạng thái cũ rồi thêm lại phiên bản mới.

## 4. Xử lý kết quả null đúng cách

Đoạn sau có nguy cơ lỗi:

```java
// Đoạn minh họa: values đang chứa 10, 20, 30, 40.
int next = values.higher(40); // Tự mở hộp null -> NullPointerException.
```

`higher` trả `Integer`, còn biến nhận là `int`. Lỗi xuất hiện khi tự mở hộp (unboxing), không phải vì phương thức điều hướng ném lỗi “không tìm thấy”.

Giữ kiểu đối tượng và kiểm tra trước:

```java
// Đoạn minh họa, đặt trong ngữ cảnh có biến values.
Integer next = values.higher(40);
if (next == null) {
    System.out.println("Khong co muc tiep theo");
} else {
    System.out.println(next);
}
```

Không tự thay `null` bằng 0, -1 hoặc một giá trị “đặc biệt” nếu giá trị ấy cũng hợp lệ trong miền dữ liệu. Việc chọn phương án dự phòng thuộc về nghiệp vụ.

Trong bài, mọi tập đều không chứa phần tử `null`, nên kết quả `null` được hiểu rõ là không có ứng viên. Hợp đồng `NavigableSet` nói chung cho phép cách cài đặt có chính sách null khác nhau; nếu một cách cài đặt cho chứa null, kết quả điều hướng có thể gây nhập nhằng. Với `TreeSet` theo thứ tự tự nhiên, không dùng null làm phần tử hoặc mốc tìm kiếm. Các đối tượng được truy vấn cũng phải tương thích với phép so sánh của tập; dùng kiểu không so sánh được có thể gây `ClassCastException`.

## 5. Góc nhìn có giới hạn chỉ tìm trong vùng của nó

Giả sử:

```java
// Đoạn minh họa với values = [10, 20, 30, 40].
NavigableSet<Integer> window = values.subSet(20, true, 40, false);
```

`window` chứa `[20, 30]`: nhận đầu 20, loại đầu 40.

```text
window.ceiling(35) -> null
values.ceiling(35) -> 40
```

40 tồn tại trong tập gốc nhưng không thuộc góc nhìn. Phương thức điều hướng không “thoát khỏi” giới hạn để lấy nó.

Điều này hữu ích khi đang chọn phần tử trong một phạm vi hợp lệ, chẳng hạn khung giờ hoặc khoảng giá đã lọc. Nếu nghiệp vụ muốn tìm trong toàn bộ tập, hãy gọi trên tập gốc. Nếu muốn tìm trong khoảng giới hạn, `null` phải được giải thích là “không có ứng viên trong khoảng”.

Các góc nhìn liên kết không phải bản chụp độc lập. Khi tập gốc thay đổi, kết quả của truy vấn trên góc nhìn có thể đổi theo. Chỉ đọc một kết quả cũng không đặt chỗ hoặc khóa phần tử đó cho bước xử lý tiếp theo.

## 6. Chương trình hoàn chỉnh để đối chiếu hành vi

Lưu thành **NavigableBoundaries.java**. Chương trình chạy bằng Java 17 trở lên, in đủ trường hợp mốc có sẵn, mốc vắng, ngoài biên, thứ tự giảm, góc nhìn có giới hạn và so sánh đối tượng.

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableBoundaries {
    record Price(long amount, String label) { }

    static void printRow(NavigableSet<Integer> set, int target) {
        System.out.printf("%d | %s | %s | %s | %s%n",
                target, set.lower(target), set.floor(target),
                set.ceiling(target), set.higher(target));
    }

    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40));
        System.out.println("Ascending: " + values);
        System.out.println("x | lower | floor | ceiling | higher");
        for (int target : new int[]{5, 10, 20, 25, 40, 45}) {
            printRow(values, target);
        }

        System.out.println("Descending: " + values.descendingSet());
        printRow(values.descendingSet(), 20);
        printRow(values.descendingSet(), 25);
        System.out.println("Unchanged: " + values);

        Integer next = values.higher(40);
        System.out.println("Next after 40: " +
                (next == null ? "none" : next));

        NavigableSet<Integer> window = values.subSet(20, true, 40, false);
        System.out.println("Window: " + window);
        System.out.println("Window ceiling(35): " + window.ceiling(35));
        System.out.println("Full ceiling(35): " + values.ceiling(35));

        NavigableSet<Price> prices =
                new TreeSet<>(Comparator.comparingLong(Price::amount));
        prices.add(new Price(100, "basic"));
        prices.add(new Price(200, "standard"));
        prices.add(new Price(300, "premium"));
        Price lookup = new Price(200, "lookup");
        System.out.println("Object floor: " + prices.floor(lookup));
        System.out.println("Object ceiling: " + prices.ceiling(lookup));
        System.out.println("Object lower: " + prices.lower(lookup));
        System.out.println("Object higher: " + prices.higher(lookup));
        System.out.println("Duplicate amount added: " +
                prices.add(new Price(200, "alternative")));
        System.out.println("Object count: " + prices.size());

        NavigableSet<Integer> empty = new TreeSet<>();
        System.out.printf("Empty: %s, %s, %s, %s%n",
                empty.lower(20), empty.floor(20),
                empty.ceiling(20), empty.higher(20));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NavigableBoundaries.java
java NavigableBoundaries
```

Kết quả chuẩn:

```text
Ascending: [10, 20, 30, 40]
x | lower | floor | ceiling | higher
5 | null | null | 10 | 10
10 | null | 10 | 10 | 20
20 | 10 | 20 | 20 | 30
25 | 20 | 20 | 30 | 30
40 | 30 | 40 | 40 | null
45 | 40 | 40 | null | null
Descending: [40, 30, 20, 10]
20 | 30 | 20 | 20 | 10
25 | 30 | 30 | 20 | 20
Unchanged: [10, 20, 30, 40]
Next after 40: none
Window: [20, 30]
Window ceiling(35): null
Full ceiling(35): 40
Object floor: Price[amount=200, label=standard]
Object ceiling: Price[amount=200, label=standard]
Object lower: Price[amount=100, label=basic]
Object higher: Price[amount=300, label=premium]
Duplicate amount added: false
Object count: 3
Empty: null, null, null, null
```

Dòng `Unchanged` cho thấy các truy vấn trước đó không xóa phần tử. Bốn phương thức đang học chỉ tìm; các thao tác như `pollFirst`, `pollLast` mới lấy rồi loại phần tử.

## 7. Chọn đúng phương thức theo yêu cầu nghiệp vụ

Các tình huống dưới đây giả sử thứ tự tăng dần.

### 7.1. Ngưỡng bắt đầu có hiệu lực: floor

Nếu các mốc cấu hình là 0, 100 và 500, cấu hình tại mốc nào được áp dụng từ mốc đó cho đến trước mốc kế tiếp, thì giá trị 320 dùng mốc `floor(320) = 100`.

Dùng `lower` ở đúng mốc 100 sẽ lấy mốc trước đó và áp dụng sai quy tắc “có hiệu lực từ 100”. Phải quyết định rõ đầu mốc có được nhận hay không trước khi viết mã.

Nếu không có mốc thấp hơn hoặc bằng đầu vào, cần quy định hành vi: dùng mặc định, từ chối hoặc yêu cầu cấu hình. Không để một phép mở hộp null quyết định hộ nghiệp vụ.

### 7.2. Tìm mức đáp ứng tối thiểu: ceiling

Các dung lượng hỗ trợ là 128, 256, 512. Nhu cầu 200 chọn `ceiling(200) = 256`. Nhu cầu đúng 256 vẫn chọn 256, không cần chuyển sang mức 512.

Dùng `higher` sẽ bỏ qua lựa chọn bằng nhu cầu và có thể làm tăng chi phí không cần thiết. Nếu nhu cầu vượt 512, `null` nghĩa là chưa có mức nào đáp ứng.

### 7.3. Chuyển sang phần tử kế tiếp hoặc trước đó: higher/lower

Một màn hình cần nút “trang có mã kế tiếp” sau mã đang xem thì dùng `higher(currentId)`; nút quay về mã trước dùng `lower(currentId)`.

Nếu dùng `ceiling(currentId)` trên mã vẫn đang có trong tập, kết quả lại chính mã hiện tại. Trong vòng lặp, điều này có thể làm chương trình không tiến lên.

Bốn phương thức không lưu lịch sử duyệt. Với cùng một tập không đổi và cùng x, gọi `higher(x)` nhiều lần vẫn cho cùng kết quả; muốn tiếp tục phải cập nhật mốc thành kết quả vừa nhận.

### 7.4. “Gần nhất” theo khoảng cách cần thêm quy tắc

`floor` và `ceiling` chỉ đưa ra ứng viên hai phía. Không phương thức nào tự so sánh khoảng cách tuyệt đối để tìm phần tử gần x nhất.

Ví dụ tập `[10, 100]`, mốc 90:

```text
floor(90)   -> 10, khoảng cách 80
ceiling(90) -> 100, khoảng cách 10
```

Muốn chọn gần nhất về giá trị số, phải kiểm tra cả hai phía, xử lý phía không tồn tại và định nghĩa cách giải quyết khi khoảng cách bằng nhau. Với `Integer`, chuyển sang `long` trước phép trừ để tránh tràn. Với chuỗi hoặc một comparator nghiệp vụ, có thể không tồn tại khái niệm khoảng cách có ý nghĩa.

## 8. Cơ chế tìm kiếm và giới hạn hiệu năng

Có thể hình dung `TreeSet` tìm dọc theo cây tìm kiếm có thứ tự và giữ ứng viên tốt nhất đã gặp. Ví dụ tìm `floor(x)`:

- Nếu gặp nút bằng x theo comparator, đã có kết quả.
- Nếu nút nhỏ hơn x, nó là một ứng viên; thử đi về phía lớn hơn để tìm ứng viên sát hơn.
- Nếu nút lớn hơn x, phải tìm ở phía nhỏ hơn.
- Khi không đi tiếp được, trả ứng viên đã giữ hoặc `null`.

Đó là cách lý giải thuật toán, không có nghĩa người dùng cần tự truy cập các nút bên trong `TreeSet`.

Với `TreeSet` dựa trên cây cân bằng, các truy vấn điều hướng đi theo chiều cao cây, nên có chi phí O(log n) lần so sánh. Nếu comparator phải xử lý chuỗi dài hoặc logic đắt, chi phí thực còn phụ thuộc mỗi lần so sánh. `NavigableSet` là giao diện hành vi; không suy ra mọi cách cài đặt đều có cùng độ phức tạp.

Tạo cả một `TreeSet` từ dữ liệu chỉ để hỏi một lần có thể tốn nhiều hơn quét dữ liệu một lần. Cấu trúc có thứ tự phát huy giá trị khi cần duy trì dữ liệu và truy vấn nhiều lần. Khi duyệt tuần tự toàn bộ tập không thay đổi, iterator thường hợp lý hơn liên tục tìm `higher` cho từng phần tử; n lần tìm lại có thể thành O(n log n).

`TreeSet` không tự đồng bộ truy cập nhiều luồng. Đặc biệt, chuỗi “tìm ứng viên rồi xử lý/xóa ứng viên” là nhiều bước; kết quả tìm được không bảo đảm vẫn còn đó nếu có luồng khác thay đổi tập. Cần một cơ chế sở hữu/đồng bộ phù hợp khi tính đúng đắn phụ thuộc cả chuỗi thao tác.

## 9. Lỗi thường gặp

| Hiểu nhầm | Cách nhận biết và sửa |
| --- | --- |
| `lower` cũng nhận bằng | Thử mốc có trong tập; dùng `floor` nếu nhận bằng |
| `higher` giống `ceiling` | Với mốc hiện có, `higher` phải đi tiếp |
| Không có kết quả sẽ ném lỗi | Giữ kiểu E và kiểm tra `null` |
| Kết quả là vị trí/chỉ số | Kết quả là phần tử thực trong tập |
| x phải nằm trong tập | Thử mốc nằm giữa hai phần tử |
| `lower` luôn là số nhỏ hơn | Đối chiếu comparator và góc nhìn giảm dần |
| floor/ceiling dùng `equals` để nhận bằng | Kiểm tra điều kiện comparator trả 0 |
| Truy vấn tự xóa phần tử | Kiểm tra tập trước/sau; phân biệt với thao tác `poll` |
| Kết quả của góc nhìn có thể vượt giới hạn | Truy vấn chỉ xét phần tử thuộc góc nhìn |
| “Sát mốc” đồng nghĩa “gần nhất về khoảng cách” | Lấy hai ứng viên rồi áp dụng quy tắc khoảng cách |

## 10. Bài tập tự kiểm chứng

1. Với `[2, 6, 9]`, dự đoán đủ bốn kết quả cho x bằng 1, 2, 5, 6 và 10. Riêng x = 6 phải cho `2, 6, 6, 9` theo thứ tự lower, floor, ceiling, higher.
2. Đổi sang `descendingSet()` rồi kiểm tra x = 6. Kết quả phải là `9, 6, 6, 2`; giải thích bằng comparator thay vì thuộc lòng giá trị.
3. Viết hàm chọn dung lượng nhỏ nhất đáp ứng yêu cầu với tập `[128, 256, 512]`. Yêu cầu 256 chọn 256; yêu cầu 513 phải thể hiện rõ không có lựa chọn.
4. Với tập `[10, 20, 30, 40]`, tạo góc nhìn chỉ nhận đoạn `[20, 40)`. Giải thích vì sao `floor(100)` trên góc nhìn trả 30 còn trên tập gốc trả 40.
5. Viết hàm tìm số nguyên gần mốc nhất. Thử tập rỗng, một phần tử, hai phía bằng khoảng cách và các giá trị gần `Integer.MIN_VALUE`/`Integer.MAX_VALUE`. Nêu rõ quy tắc khi hai ứng viên cách đều.

Trước mỗi truy vấn, hãy xác định thứ tự của tập, phía cần tìm, việc có nhận bằng và hành vi khi không có ứng viên. Bốn quyết định này đủ để lựa chọn đúng giữa `lower`, `floor`, `ceiling` và `higher`.
