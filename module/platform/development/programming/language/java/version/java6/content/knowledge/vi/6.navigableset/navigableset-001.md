# Tập hợp có thứ tự và nhu cầu tìm phần tử gần nhất

## 1. Từ “có hay không” đến “nằm ở đâu”

Giả sử một hệ thống hỗ trợ các mức dung lượng 10, 20, 35 và 50 GB. Khách hàng yêu cầu 26 GB. Câu hỏi “có mức 26 hay không?” chỉ cho biết không có, nhưng chưa giúp chọn mức phù hợp.

Có ít nhất ba yêu cầu khác nhau:

- Muốn mức lớn nhất **không vượt quá** 26: chọn 20.
- Muốn mức nhỏ nhất **đáp ứng ít nhất** 26: chọn 35.
- Muốn mức có **khoảng cách số học nhỏ nhất** tới 26: so sánh 20 và 35, rồi chọn 20.

Đây là lý do cần một tập hợp duy trì thứ tự và cho phép tìm lân cận của một giá trị. Trong Java, `NavigableSet<E>` diễn đạt khả năng ấy. Nó mở rộng `SortedSet<E>` bằng những phép tìm phần tử gần một mốc theo thứ tự của tập hợp. `TreeSet<E>` là một cách cài đặt thường dùng.

Bài này xây dựng cách nghĩ trước: **tập hợp duy nhất → quy tắc so sánh → vị trí tương đối → quy tắc lựa chọn của nghiệp vụ**. Các API được dùng vẫn áp dụng trong Java hiện đại; ví dụ chạy được từ Java 17 trở lên.

## 2. “Tập hợp có thứ tự” gồm hai điều kiện

### Tập hợp: không giữ nhiều phần tử được coi là trùng

Nếu cần các mức dung lượng khả dụng, hai lần thêm mức 20 không tạo ra hai mức 20 trong `TreeSet<Integer>`.

Điều này phù hợp với “các giá trị được phép”. Nhưng nếu hai đơn hàng khác nhau đều có giá 20, chỉ lưu giá vào tập hợp sẽ làm mất thông tin số lượng đơn hàng. Khi đó cần mô hình dữ liệu khác hoặc khóa phân biệt đối tượng.

### Có thứ tự: thứ tự do so sánh quyết định

`SortedSet` duy trì thứ tự tự nhiên của phần tử hoặc thứ tự do `Comparator` cung cấp. Duyệt tập hợp đi theo thứ tự ấy. `SortedSet` không có nghĩa là giữ thứ tự chèn; “đầu tiên” và “cuối cùng” gắn với phép so sánh. Xem [SortedSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/SortedSet.html).

Ví dụ với số nguyên và thứ tự tự nhiên:

```text
Thứ tự thêm: 35, 10, 50, 20
Thứ tự duyệt TreeSet: 10, 20, 35, 50
```

Không nên hiểu “có thứ tự” là “có chỉ số”. Giao diện `NavigableSet` không có `get(2)` để lấy phần tử thứ ba như `List`. Điểm mạnh ở đây là tra cứu theo **giá trị và quan hệ thứ tự**.

Khi nhìn tên kiểu biến, có thể lần theo các khả năng:

```text
Set
  -> giữ các phần tử không trùng
SortedSet
  -> thêm quy tắc thứ tự
NavigableSet
  -> thêm tìm lân cận theo một mốc
TreeSet
  -> một lớp cài đặt cụ thể
```

Đây là quan hệ khả năng, không phải lời khuyên rằng mọi bài toán đều cần lớp ở cuối sơ đồ.

## 3. Xác định “gần nhất” theo phía nào

Với tập hợp tăng dần `[10, 20, 35, 50]`, bốn phương thức giúp diễn đạt điều kiện một cách chính xác:

| Phương thức | Ý nghĩa trong thứ tự tự nhiên tăng dần | Với mốc 26 | Với mốc 20 |
| --- | --- | --- | --- |
| `lower(x)` | Phần tử lớn nhất nhỏ hơn x | 20 | 10 |
| `floor(x)` | Phần tử lớn nhất nhỏ hơn hoặc bằng x | 20 | 20 |
| `ceiling(x)` | Phần tử nhỏ nhất lớn hơn hoặc bằng x | 35 | 20 |
| `higher(x)` | Phần tử nhỏ nhất lớn hơn x | 35 | 35 |

Nếu không có phần tử thỏa điều kiện, kết quả là `null`. Những phép tìm này chỉ đọc, không xóa phần tử. Xem [NavigableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableSet.html).

Phân biệt hai cặp quan trọng:

- `floor/ceiling` chấp nhận chính mốc đang tìm nếu mốc có trong tập hợp.
- `lower/higher` bỏ qua phần tử bằng mốc, để tìm phần tử thực sự đứng trước hoặc sau.

Ví dụ nghiệp vụ:

- Trần chi tiêu 26: `floor(26)` tìm mức cao nhất còn nằm trong ngân sách.
- Phải đáp ứng ít nhất 26 GB: `ceiling(26)` tìm mức đủ gần nhất ở phía trên.
- Tìm bản ghi kế tiếp sau mã 20: `higher(20)` tránh trả lại chính mã 20.

Có thể vẽ vị trí truy vấn mà không cần mốc phải tồn tại trong tập hợp:

```text
10 -------- 20 ---- 26 ------ 35 -------- 50
            ^                 ^
         floor(26)        ceiling(26)
```

## 4. Gần theo thứ tự khác gần theo khoảng cách

`NavigableSet` không có phương thức chung `nearest(x)` trả phần tử có khoảng cách nhỏ nhất.

Lý do: **so sánh thứ tự chưa định nghĩa khoảng cách**. Với mã sản phẩm hoặc chuỗi, biết A đứng trước B không đủ để nói A cách B bao xa về mặt nghiệp vụ. `Comparator` quy định quan hệ trước/sau/bằng trong thứ tự; độ lớn của số nguyên do `compare` trả về không phải khoảng cách. Xem [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Với số nguyên được xếp theo thứ tự tự nhiên, ta có thể tự định nghĩa khoảng cách là chênh lệch tuyệt đối. Khi đó chỉ cần hai ứng viên:

1. `floor(x)`: ứng viên phía không vượt quá x.
2. `ceiling(x)`: ứng viên phía không nhỏ hơn x.
3. Nếu thiếu một phía, chọn phía còn lại.
4. Nếu có cả hai, so khoảng cách; khi hòa phải có quy tắc rõ ràng.

Vì sao không cần xét mọi phần tử? Ở phía dưới x, mọi phần tử khác đều không lớn hơn `floor(x)`, nên không thể gần x hơn theo khoảng cách số học. Lập luận tương tự áp dụng cho `ceiling(x)` ở phía trên.

Đây là suy luận cho **thứ tự số học tăng dần và khoảng cách số học**. Không áp dụng máy móc với thứ tự theo độ dài chuỗi, theo mức ưu tiên hoặc một `Comparator` tùy ý.

## 5. Chương trình Java: tìm lân cận và chọn mức gần nhất

Chương trình dưới đây quy định:

- Dữ liệu là số nguyên trong `TreeSet` có thứ tự tự nhiên.
- Khoảng cách là chênh lệch số học.
- Nếu hai mức cách đều, chọn mức nhỏ hơn.
- Nếu tập hợp rỗng, không có kết quả.

Lưu tệp `NearestLevelDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.OptionalInt;
import java.util.TreeSet;

public class NearestLevelDemo {
    // Precondition: values uses natural ascending integer order.
    // Tie rule: prefer the smaller value.
    static OptionalInt nearest(NavigableSet<Integer> values, int target) {
        Integer below = values.floor(target);
        Integer above = values.ceiling(target);

        if (below == null && above == null) {
            return OptionalInt.empty();
        }
        if (below == null) {
            return OptionalInt.of(above);
        }
        if (above == null) {
            return OptionalInt.of(below);
        }

        long distanceBelow = (long) target - below;
        long distanceAbove = (long) above - target;
        return OptionalInt.of(
                distanceBelow <= distanceAbove ? below : above);
    }

    static String show(OptionalInt result) {
        return result.isPresent()
                ? Integer.toString(result.getAsInt())
                : "none";
    }

    public static void main(String[] args) {
        NavigableSet<Integer> levels =
                new TreeSet<>(List.of(35, 10, 50, 20));

        System.out.println("levels=" + levels);
        System.out.println("add.20=" + levels.add(20));
        System.out.println("contains.26=" + levels.contains(26));
        System.out.println("lower.20=" + levels.lower(20));
        System.out.println("floor.20=" + levels.floor(20));
        System.out.println("ceiling.20=" + levels.ceiling(20));
        System.out.println("higher.20=" + levels.higher(20));
        System.out.println("floor.26=" + levels.floor(26));
        System.out.println("ceiling.26=" + levels.ceiling(26));

        for (int target : new int[] {26, 30, 5, 60, 20}) {
            System.out.println("nearest." + target + "="
                    + show(nearest(levels, target)));
        }

        NavigableSet<Integer> tie =
                new TreeSet<>(List.of(10, 20));
        System.out.println("tie.15=" + show(nearest(tie, 15)));

        NavigableSet<Integer> empty = new TreeSet<>();
        System.out.println("empty="
                + show(nearest(empty, 26)));

        NavigableSet<Integer> extremes = new TreeSet<>(
                List.of(Integer.MIN_VALUE, Integer.MAX_VALUE));
        System.out.println("extreme.0="
                + show(nearest(extremes, 0)));

        levels.add(25);
        System.out.println("after.add.25=" + levels);
        System.out.println("nearest.26.after="
                + show(nearest(levels, 26)));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```shell
javac --release 17 NearestLevelDemo.java
java NearestLevelDemo
```

Stdout chính xác:

```text
levels=[10, 20, 35, 50]
add.20=false
contains.26=false
lower.20=10
floor.20=20
ceiling.20=20
higher.20=35
floor.26=20
ceiling.26=35
nearest.26=20
nearest.30=35
nearest.5=10
nearest.60=50
nearest.20=20
tie.15=10
empty=none
extreme.0=2147483647
after.add.25=[10, 20, 25, 35, 50]
nearest.26.after=25
```

Cách đọc kết quả:

- `contains(26)` chỉ trả lời không có đúng giá trị 26. Hai phép điều hướng vẫn tìm được 20 và 35.
- Với 26, khoảng cách tới 20 là 6, tới 35 là 9; chọn 20.
- Với 30, khoảng cách tới 20 là 10, tới 35 là 5; chọn 35.
- Mốc 5 thấp hơn mọi mức, nên chỉ có ứng viên trên; mốc 60 cao hơn mọi mức, nên chỉ có ứng viên dưới.
- Trường hợp 15 trong `[10, 20]` kiểm chứng quy tắc hòa: chọn 10.
- Sau khi thêm 25, truy vấn 26 trả 25 mà không cần tự sắp xếp lại một danh sách.

Hàm `nearest` nhận `NavigableSet<Integer>` để dùng hợp đồng điều hướng, nhưng thuật toán có tiền điều kiện về thứ tự. Người gọi không được truyền một tập hợp có comparator khác rồi kỳ vọng cùng ý nghĩa khoảng cách.

## 6. Những điều kiện dễ bị bỏ sót

### Kết quả có thể không tồn tại

`floor` trả `null` nếu mốc nhỏ hơn mọi phần tử. `ceiling` trả `null` nếu mốc lớn hơn mọi phần tử. Tập hợp rỗng khiến cả hai không có kết quả.

Đừng nhận thẳng kết quả vào biến `int` khi chưa kiểm tra: tự mở hộp `null` gây `NullPointerException`. Ví dụ dùng `Integer` cho hai ứng viên và dùng `OptionalInt` để biểu diễn việc hàm chọn mức không có kết quả.

Với `TreeSet<Integer>` sử dụng thứ tự tự nhiên như trong chương trình, không thêm `null`. Nhờ vậy `null` trả về từ truy vấn có ý nghĩa rõ ràng là không có ứng viên.

### Tránh tràn số khi tính khoảng cách

Hai giá trị `int` hợp lệ có thể có hiệu vượt miền `int`. Phải chuyển sang `long` **trước khi trừ**:

```java
long distance = (long) target - below; // Chuyển kiểu trước phép trừ.
```

Không thay bằng `(long) (target - below)`: phép trừ bên trong đã thực hiện theo `int`, nên có thể tràn trước khi chuyển kiểu. Cũng không mặc định `Math.abs(target - value)` an toàn với mọi cặp số nguyên.

Trong ví dụ hai cực trị, 0 cách `Integer.MAX_VALUE` là 2.147.483.647 và cách `Integer.MIN_VALUE` là 2.147.483.648. Chọn cực đại là đúng, không phải trường hợp hòa.

### Comparator quyết định cả thứ tự lẫn khái niệm trùng trong TreeSet

`TreeSet` dùng phép so sánh để nhận biết hai phần tử tương đương: nếu so sánh trả 0, phần tử thứ hai được xem là đã có. Thứ tự nên nhất quán với `equals` để đáp ứng đúng hợp đồng chung của `Set`. Xem [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Ví dụ, chỉ so sánh người theo tuổi sẽ khiến hai người cùng tuổi bị coi là trùng trong tập hợp ấy. Nếu bài toán cần giữ cả hai, phải thiết kế thêm khóa phân biệt và định nghĩa sự bằng nhau phù hợp, hoặc chọn cấu trúc biểu diễn nhóm người theo tuổi.

Tương tự, không sửa thuộc tính dùng để so sánh của một đối tượng khi nó còn nằm trong cây. Nếu cần cập nhật thuộc tính đó, hãy loại đối tượng khỏi tập hợp trước, thay đổi rồi thêm lại để thứ tự được thiết lập đúng.

## 7. Khi nào nên chọn NavigableSet?

`NavigableSet` có giá trị khi ứng dụng cần trả lời nhiều câu hỏi theo mốc trong lúc dữ liệu cũng được thêm/xóa: mức giá sát ngân sách, phiên bản đứng trước/sau một phiên bản, hoặc thời điểm gần phía trước/phía sau một mốc.

Với `TreeSet`, các thao tác cơ bản `add`, `remove`, `contains` có chi phí O(log n); nó dựa trên `TreeMap`. Đây là đặc tính của lớp cài đặt, không phải cam kết độ phức tạp cho mọi lớp thực thi `NavigableSet`. `TreeSet` cũng không tự đồng bộ để phục vụ truy cập ghi đồng thời. Xem [đặc tính TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Chọn dựa trên câu hỏi thực tế:

| Câu hỏi chính | Hướng cấu trúc |
| --- | --- |
| Chỉ cần biết giá trị có tồn tại, không cần thứ tự | Xem xét `HashSet` |
| Cần giữ thứ tự thêm | Xem xét `LinkedHashSet` |
| Cần duy trì giá trị duy nhất theo thứ tự và tìm lân cận | `NavigableSet`, thường dùng `TreeSet` |
| Cần giữ nhiều lần xuất hiện của cùng giá trị | `List` hoặc mô hình đếm/nhóm phù hợp |
| Dữ liệu gần như cố định, cần truy cập theo chỉ số | Xem xét danh sách/mảng đã sắp xếp và tìm kiếm nhị phân |
| Cần lấy thêm thông tin gắn với khóa lân cận | Xem xét `NavigableMap` |

Không cần đổi sang cây chỉ vì có một truy vấn duy nhất trên vài phần tử. Nhưng khi câu hỏi “ngay trước/ngay sau mốc nào?” lặp lại và dữ liệu thay đổi, việc để cấu trúc duy trì thứ tự giúp tránh tự quét toàn bộ dữ liệu ở mỗi lần hỏi.

## 8. Tự kiểm tra mô hình

Với tập hợp tự nhiên tăng dần `[100, 150, 220]`:

1. Ngân sách tối đa 180 cần `floor` hay `ceiling`? Kết quả nào?
2. Yêu cầu dung lượng ít nhất 180 cần phương thức nào? Kết quả nào?
3. Tìm mức ngay sau 150, không chấp nhận chính 150: dùng phương thức nào?
4. Nếu cần mức gần 180 nhất theo khoảng cách, phải so hai ứng viên nào?
5. Hai sản phẩm khác nhau cùng giá 150 có được giữ đầy đủ nếu chỉ lưu giá vào `TreeSet<Integer>` không?

Định hướng trả lời: (1) `floor(180)=150`; (2) `ceiling(180)=220`; (3) `higher(150)=220`; (4) so 150 và 220, chọn 150 vì khoảng cách 30 nhỏ hơn 40; (5) không, tập hợp giá không biểu diễn được hai sản phẩm khác nhau.

Trước khi dùng một phép tìm lân cận, hãy phát biểu đủ ba điều: thứ tự đang dùng là gì, điều kiện có chấp nhận bằng mốc không, và nếu cần “gần nhất” thì khoảng cách cùng quy tắc hòa được định nghĩa thế nào.
