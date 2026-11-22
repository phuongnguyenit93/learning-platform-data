# Comparator, equals và tính nhất quán của thứ tự trong NavigableSet

## 1. Một tập có thứ tự phải trả lời hai câu hỏi

Khi dùng `NavigableSet<E>`, ta thường quan tâm phần tử nào đứng trước, phần tử nào đứng sau và hàng xóm của một mốc là gì. Nhưng cấu trúc này còn phải quyết định **hai phần tử có được xem là cùng một phần tử hay không**.

Với `TreeSet`, cả việc tìm vị trí lẫn nhận diện phần tử trùng đều dựa vào phép so sánh:

- Không truyền comparator: dùng thứ tự tự nhiên do `Comparable.compareTo` định nghĩa.
- Truyền `Comparator`: dùng comparator đó.
- Hai phần tử so sánh ra 0 được `TreeSet` xem là cùng một vị trí, dù `equals` có thể trả `false`.

Vì vậy, comparator trong tập có thứ tự không chỉ để “sắp xếp cho đẹp”. Nó tham gia trực tiếp vào `add`, `contains`, `remove`, các truy vấn điều hướng và ranh giới của góc nhìn khoảng.

Bài này dùng API hiện hành và ví dụ Java 17 trở lên. `TreeSet` là cách cài đặt cụ thể để quan sát hành vi của một `NavigableSet`.

## 2. Phân biệt ba khái niệm

| Khái niệm | Câu hỏi được trả lời | Cơ chế |
| --- | --- | --- |
| Thứ tự | a đứng trước hay sau b? | Dấu của `compare(a, b)` |
| Tương đương theo thứ tự | a và b có chung một vị trí so sánh không? | `compare(a, b) == 0` |
| Bằng theo đối tượng | a và b có bằng nhau theo mô hình đối tượng không? | `a.equals(b)` |

### 2.1. Chỉ dấu của compare có ý nghĩa

Một comparator trả:

```text
âm   -> a đứng trước b
0    -> a và b tương đương theo thứ tự
dương -> a đứng sau b
```

Nó không bắt buộc chỉ trả -1, 0 hoặc 1. Đừng viết mã như `compare(a, b) == 1` để kiểm tra “lớn hơn”; phải dùng `> 0`.

Giá trị trả về cũng không phải khoảng cách. Ví dụ một comparator chuỗi trả số âm không cung cấp một đại lượng “chuỗi a gần chuỗi b bao nhiêu”.

### 2.2. Thứ tự nhất quán với equals

Với mọi a, b hợp lệ trong miền dữ liệu, tính nhất quán yêu cầu:

```text
(compare(a, b) == 0) có cùng kết quả boolean với a.equals(b)
```

Có hai chiều phải đúng:

1. Nếu `a.equals(b)` là `true`, comparator phải trả 0.
2. Nếu comparator trả 0, `a.equals(b)` phải là `true`.

Nếu chỉ đúng một chiều thì vẫn chưa nhất quán. Đây là định nghĩa trong [Comparator API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Một comparator có thể tuân thủ các quy tắc so sánh nhưng không nhất quán với `equals`. Trường hợp đó khác hẳn comparator sai bắc cầu hoặc đổi kết quả tùy lần gọi. Cần phân biệt:

- **Thứ tự hợp lệ nhưng không nhất quán với equals:** hành vi tập theo comparator vẫn xác định, nhưng không tuân thủ đầy đủ hợp đồng chung của `Set`.
- **Phép so sánh không tạo được thứ tự hợp lệ:** các giả định tìm kiếm/sắp xếp không còn đáng tin cậy.

## 3. Vì sao TreeSet có thể bỏ qua một đối tượng khác equals?

Xét bản ghi:

```java
// Đoạn định nghĩa minh họa.
record Student(int id, String name) { }
```

`record` này mặc định dùng cả id và name trong `equals`. Do đó:

```text
Student(7, "An").equals(Student(7, "Binh")) -> false
```

Nếu comparator chỉ xét id:

```java
// Đoạn minh họa, cần import java.util.Comparator.
Comparator<Student> byId = Comparator.comparingInt(Student::id);
```

Hai đối tượng trên so sánh bằng nhau vì cùng id 7.

Giả sử tập đã chứa An rồi ta thực hiện các thao tác với Binh:

| Thao tác | Kết quả | Lý do |
| --- | --- | --- |
| `add(binh)` | `false` | Đã có một phần tử so sánh bằng |
| `contains(binh)` | `true` | Tìm được vị trí có comparator bằng 0 |
| `floor(binh)` | Trả đối tượng An đang lưu | An là ứng viên so sánh bằng mốc |
| `ceiling(binh)` | Trả đối tượng An đang lưu | Cũng chấp nhận bằng theo comparator |
| `remove(binh)` | Xóa An khỏi tập | Phép tìm để xóa dùng cùng quan hệ so sánh |

`add` trả `false` không có nghĩa đối tượng cũ được cập nhật thành đối tượng mới. Nếu muốn giữ “mỗi id một hồ sơ mới nhất”, cần thiết kế thao tác cập nhật hoặc dùng cấu trúc ánh xạ theo id phù hợp; đừng dựa vào `TreeSet.add` để ghi đè dữ liệu.

Các quan hệ bằng theo comparator cũng ảnh hưởng `lower` và `higher`: hai phương thức này bỏ qua phần tử so sánh bằng mốc và tìm ở phía nghiêm ngặt tương ứng.

TreeSet công bố rõ đặc điểm này trong [TreeSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html). Nó không dùng `hashCode` để quyết định vị trí hoặc phần tử trùng.

## 4. Sửa thiết kế dựa trên ý nghĩa dữ liệu

### 4.1. Nếu hai trường đều tạo nên giá trị của Student

Nếu hai bản ghi khác tên được xem là hai giá trị khác nhau, comparator phải phân biệt chúng:

```java
// Đoạn minh họa với Student có name khác null.
Comparator<Student> byAllFields =
        Comparator.comparingInt(Student::id)
                .thenComparing(Student::name);
```

Comparator xét id trước; chỉ khi id bằng mới so tên. Với record gồm đúng hai trường trên và name là chuỗi không null, comparator trả 0 đúng khi cả hai trường bằng nhau, phù hợp với `equals`.

`thenComparing` là khóa phân biệt tiếp theo, không phải thủ thuật mặc định để thêm vào mọi comparator. Nếu mô hình định nghĩa đối tượng chỉ bằng id, việc so thêm tên lại có thể làm hai đối tượng `equals` bằng nhau nhận hai vị trí khác nhau.

Cần chốt ý nghĩa “cùng một phần tử” trước rồi mới viết cả `equals` và comparator.

### 4.2. Nếu id là định danh duy nhất

Nếu tên chỉ là thông tin thay đổi của cùng một học viên, lựa chọn có thể là:

- Mô hình đối tượng có `equals`/`hashCode` dựa trên id và comparator cũng dựa trên id.
- Hoặc lưu khóa id trong một tập có thứ tự, còn dữ liệu hồ sơ ở cấu trúc ánh xạ.
- Hoặc dùng một `NavigableMap<Integer, Student>` nếu cần mỗi id gắn một hồ sơ và điều hướng theo id.

Không sửa `equals` chỉ để làm một comparator đang có trở nên “đúng” nếu điều đó làm sai ý nghĩa đối tượng trong toàn bộ ứng dụng.

Khi tự cài `equals`, phải giữ đúng hợp đồng `hashCode`: các đối tượng bằng nhau có cùng mã băm. `TreeSet` không dùng mã băm để tìm phần tử, nhưng cùng đối tượng có thể còn đi vào `HashSet`, `HashMap` hoặc trở thành khóa ở nơi khác.

### 4.3. Nếu chỉ muốn trình bày theo một tiêu chí

Giả sử muốn hiển thị danh sách học viên theo tên, trong khi định danh vẫn là id. Hai học viên trùng tên vẫn phải tồn tại.

Một `List` được sắp xếp theo tên có thể phù hợp hơn một `TreeSet` chỉ so tên. Sắp xếp danh sách không biến các phần tử cùng khóa sắp xếp thành một phần tử duy nhất; tập có thứ tự thì có.

Nếu thật sự cần `NavigableSet`, hãy định nghĩa thứ tự đầy đủ và quan hệ bằng nhất quán với loại giá trị đang lưu, thay vì vô tình dùng tiêu chí hiển thị làm định danh.

## 5. BigDecimal: ví dụ chuẩn về hai cách nhìn “bằng”

Hai giá trị:

```java
// Đoạn minh họa, cần import java.math.BigDecimal.
BigDecimal first = new BigDecimal("4.0");
BigDecimal second = new BigDecimal("4.00");
```

Cho kết quả:

```text
first.compareTo(second) -> 0
first.equals(second)    -> false
```

So sánh thứ tự của `BigDecimal` nhìn vào giá trị số, còn `equals` phân biệt cả cách biểu diễn qua scale. Vì vậy thứ tự tự nhiên của `BigDecimal` không nhất quán với `equals`; đây là đặc điểm hiện hành được ghi trong [BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

Hệ quả: tập băm có thể chứa cả 4.0 và 4.00, còn `TreeSet` dùng thứ tự tự nhiên xem chúng là cùng vị trí.

Một hệ quả ít trực quan hơn xuất hiện khi so sánh hai tập có một phần tử:

```text
tree chứa 4.0
hash chứa 4.00

tree.equals(hash) -> true
hash.equals(tree) -> false
```

Trong ví dụ này, mỗi phía kiểm tra sự hiện diện theo cách của mình. Quan hệ bằng giữa các tập bị mất tính đối xứng — chính là dấu hiệu hai cấu trúc không đang tuân thủ cùng khái niệm phần tử bằng nhau.

Điều này không có nghĩa `BigDecimal` hoặc `HashSet` bị lỗi. Nó cho thấy việc dùng thứ tự không nhất quán với `equals` trong một `Set` có ảnh hưởng vượt ra ngoài thứ tự in.

Cách xử lý phải dựa vào miền dữ liệu: có phân biệt scale không, có biểu diễn chuẩn được áp dụng nhất quán ở các biên nhập/xuất không, hay nên dùng một kiểu giá trị nghiệp vụ định nghĩa rõ quan hệ bằng? Không thể sửa tất cả tình huống bằng cách tùy tiện gọi một phép chuẩn hóa ở một vị trí.

## 6. Các quy tắc của một comparator hợp lệ

Ngay cả khi đã thống nhất quan hệ bằng, phép so sánh vẫn phải có các tính chất ổn định.

### 6.1. Đảo dấu khi đổi hai đối số

Nếu a đứng trước b thì b phải đứng sau a. Dùng dấu của kết quả:

```text
sign(compare(a, b)) = -sign(compare(b, a))
```

Với chính nó, `compare(a, a)` phải bằng 0.

Không cài comparator bằng cách lúc nào cũng trả -1 khi hai đối tượng không cùng tham chiếu: nó có thể kết luận cả a trước b lẫn b trước a.

### 6.2. Bắc cầu

Nếu a đứng sau b và b đứng sau c thì a phải đứng sau c. Một quy tắc vòng tròn như “A trước B, B trước C, C trước A” không tạo được thứ tự cho cây tìm kiếm.

Comparator không nên phụ thuộc kết quả ngẫu nhiên, thời gian đang thay đổi hoặc bộ đếm số lần gọi.

### 6.3. Hai phần tử so sánh bằng phải có quan hệ giống nhau với phần tử thứ ba

Nếu `compare(a, b) == 0`, thì khi so với c, a và b phải cho cùng dấu kết quả. Không thể vừa nói a và b nằm cùng vị trí, vừa nói a trước c nhưng b sau c.

Đây là quy tắc khác với nhất quán với `equals`: nó chỉ nói về tính tự nhất quán bên trong phép so sánh.

### 6.4. Tránh tràn số và so sánh mơ hồ

Không dùng:

```java
// Mẫu lỗi khi dữ liệu có thể nằm gần biên int.
Comparator<Integer> broken = (a, b) -> a - b;
```

`Integer.MAX_VALUE - (-1)` tràn thành `Integer.MIN_VALUE`, làm số lớn bị kết luận đứng trước -1.

Dùng:

```java
// Mẫu đúng để so giá trị int.
Comparator<Integer> safe = Integer::compare;
```

Với nhiều khóa, dùng `comparingInt`, `comparingLong`, `comparing` và `thenComparing` để biểu đạt thứ tự rõ ràng. Không dùng phép ép hiệu số `long` về `int` để làm kết quả so sánh.

Với số thực, cần định nghĩa cách xử lý giá trị đặc biệt và tránh comparator “chênh lệch nhỏ hơn epsilon thì bằng” dùng tùy tiện. Quan hệ gần nhau có thể không bắc cầu: a gần b, b gần c nhưng a không gần c. Một quy tắc xấp xỉ dùng để kiểm tra sai số không tự trở thành thứ tự hợp lệ cho `TreeSet`.

### 6.5. Dữ liệu và comparator không đổi ý nghĩa khi phần tử đang trong tập

Nếu khóa sắp xếp là trường mutable và bị thay đổi sau khi thêm phần tử, cây không tự dời phần tử tới vị trí mới. `contains`, `remove`, `floor` hoặc `higher` có thể không còn tìm đúng theo kỳ vọng.

Ưu tiên khóa bất biến. Nếu phải cập nhật, xóa theo khóa cũ trước khi thay đổi, rồi thêm lại theo khóa mới trong một thao tác được kiểm soát.

Cũng không để comparator đọc một cấu hình bên ngoài rồi thay cấu hình ấy trong khi tập còn giữ dữ liệu. Thứ tự phải ổn định trong suốt thời gian cấu trúc dựa vào nó.

## 7. Chương trình hoàn chỉnh

Lưu thành **ComparatorConsistencyDemo.java**. Phần đầu cố ý tạo comparator không nhất quán để quan sát hậu quả; phần tiếp theo dùng comparator phù hợp với record. Không coi cấu hình sai ở phần đầu là mẫu thiết kế cho ứng dụng.

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.NavigableSet;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorConsistencyDemo {
    record Student(int id, String name) {
        Student {
            Objects.requireNonNull(name);
        }
    }

    public static void main(String[] args) {
        Student an = new Student(7, "An");
        Student binh = new Student(7, "Binh");
        Comparator<Student> byId =
                Comparator.comparingInt(Student::id);
        System.out.println("Student equals: " + an.equals(binh));
        System.out.println("By id compare: " + byId.compare(an, binh));

        NavigableSet<Student> collapsed = new TreeSet<>(byId);
        System.out.println("Add An: " + collapsed.add(an));
        System.out.println("Add Binh: " + collapsed.add(binh));
        System.out.println("Contains Binh: " + collapsed.contains(binh));
        System.out.println("Floor Binh: " + collapsed.floor(binh));
        System.out.println("Ceiling Binh: " + collapsed.ceiling(binh));
        System.out.println("Remove Binh: " + collapsed.remove(binh));
        System.out.println("Size after remove: " + collapsed.size());

        Comparator<Student> byAllFields =
                Comparator.comparingInt(Student::id)
                        .thenComparing(Student::name);
        NavigableSet<Student> consistent = new TreeSet<>(byAllFields);
        consistent.addAll(List.of(an, binh));
        System.out.println("Consistent set: " + consistent);
        System.out.println("Distinct students: " + consistent.size());
        System.out.println("Floor Binh after fix: " + consistent.floor(binh));

        BigDecimal first = new BigDecimal("4.0");
        BigDecimal second = new BigDecimal("4.00");
        System.out.println("Decimal equals: " + first.equals(second));
        System.out.println("Decimal compareTo: " + first.compareTo(second));
        Set<BigDecimal> hash = new HashSet<>(List.of(second));
        NavigableSet<BigDecimal> tree = new TreeSet<>(List.of(first));
        System.out.println("Tree equals hash: " + tree.equals(hash));
        System.out.println("Hash equals tree: " + hash.equals(tree));

        int large = Integer.MAX_VALUE;
        int negative = -1;
        System.out.println("Subtract comparator: " + (large - negative));
        System.out.println("Safe comparator: " +
                Integer.compare(large, negative));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ComparatorConsistencyDemo.java
java ComparatorConsistencyDemo
```

Kết quả chuẩn:

```text
Student equals: false
By id compare: 0
Add An: true
Add Binh: false
Contains Binh: true
Floor Binh: Student[id=7, name=An]
Ceiling Binh: Student[id=7, name=An]
Remove Binh: true
Size after remove: 0
Consistent set: [Student[id=7, name=An], Student[id=7, name=Binh]]
Distinct students: 2
Floor Binh after fix: Student[id=7, name=Binh]
Decimal equals: false
Decimal compareTo: 0
Tree equals hash: true
Hash equals tree: false
Subtract comparator: -2147483648
Safe comparator: 1
```

Các dòng `Contains Binh` và `Remove Binh` là bằng chứng quan trọng: tác động của comparator không dừng ở việc một lần `add` bị từ chối. Dòng `Floor Binh after fix` chứng minh việc thay quan hệ tương đương còn thay kết quả điều hướng.

## 8. Kiểm chứng comparator trước khi đưa vào tập

Với một tập mẫu nhỏ đại diện cho miền dữ liệu, kiểm tra theo các nhóm:

1. **Bằng thực sự:** hai đối tượng khác tham chiếu nhưng `equals` bằng nhau phải so sánh ra 0.
2. **Chỉ trùng khóa đầu:** cùng id hoặc điểm nhưng khác khóa còn lại; kết quả phải phù hợp định nghĩa bằng.
3. **Đảo đối số:** dấu phải đảo.
4. **Bộ ba:** kiểm tra bắc cầu và quan hệ với phần tử thứ ba khi hai phần tử so sánh bằng.
5. **Biên dữ liệu:** số nhỏ/lớn nhất, chuỗi rỗng, dữ liệu trùng, khóa dài.
6. **Ổn định:** cùng dữ liệu cho cùng kết quả qua nhiều lần gọi khi không có cập nhật hợp lệ.
7. **Tích hợp với tập:** xác minh `add`, `contains`, `remove`, `floor`, `ceiling` bằng các đối tượng truy vấn khác tham chiếu.

Không chỉ kiểm tra một danh sách đã được in theo đúng thứ tự. Một vài dòng in đẹp không chứng minh các quan hệ bằng hoặc bộ ba đều đúng.

Chính sách null cũng phải rõ. Comparator có thể được thiết kế cho null, nhưng điều đó không đồng nghĩa mọi thao tác hoặc cách cài đặt đều có cùng chính sách. Trong ví dụ, `Student.name` được yêu cầu khác null, nên comparator không phải tự đoán cách xếp tên null. Nếu thật sự cho phép null, hãy xác định nhất quán cách so sánh và ảnh hưởng tới kết quả điều hướng vốn có thể dùng null để báo không có phần tử.

## 9. Lỗi thường gặp

| Lỗi | Hậu quả |
| --- | --- |
| Dùng comparator chỉ cho hiển thị để tạo tập | Các đối tượng khác nhau nhưng trùng khóa bị gộp |
| Cho rằng TreeSet kiểm tra equals sau khi compare bằng 0 | Hiểu sai `add`, `contains`, `remove` |
| Thêm `thenComparing` mà không xét định danh | Có thể giữ hai phần tử equals bằng nhau |
| Chỉ kiểm tra chiều “equals thì compare bằng 0” | Bỏ sót trường hợp khác equals nhưng bị gộp |
| Dùng phép trừ làm comparator | Tràn số và sai thứ tự |
| Sửa trường sắp xếp sau khi thêm | Cấu trúc cây không được tổ chức lại |
| Dùng comparator không bắc cầu | Mất cơ sở để tìm kiếm theo cây |
| Cho rằng mọi kiểu Comparable đều nhất quán với equals | Bỏ sót trường hợp BigDecimal |
| So sánh hai tập có quan hệ bằng khác nhau | Có thể vi phạm tính đối xứng của equals |

## 10. Thực hành

1. Với record `Student(id, name)`, thêm hai đối tượng cùng id khác tên vào tập dùng comparator theo id. Dự đoán `add`, `contains`, `floor` và `remove` trước khi chạy.
2. Đổi comparator sang id rồi name. Tập phải giữ hai phần tử và truy vấn bằng đối tượng cùng hai trường phải tìm được đúng giá trị.
3. Giả sử yêu cầu mới quy định học viên chỉ bằng id. Giải thích vì sao comparator id rồi name không còn là lời giải đúng, và chọn lại mô hình dữ liệu.
4. Thử hai BigDecimal `"2.0"` và `"2.00"`. Giải thích vì sao tập băm có thể có kích thước 2 còn tập có thứ tự tự nhiên có kích thước 1.
5. Kiểm tra comparator số nguyên với `Integer.MIN_VALUE`, 0 và `Integer.MAX_VALUE`. Phiên bản dùng `Integer.compare` phải giữ đúng dấu khi đổi hai đối số.
6. Viết kiểm tra trên các bộ ba Student để xác nhận bắc cầu và tính nhất quán với equals. Đừng chỉ kiểm tra các đối tượng có id khác nhau; cần cả trường hợp trùng id khác tên.

Khi thiết kế một `NavigableSet`, hãy định nghĩa rõ quan hệ “cùng một phần tử”, rồi bảo đảm thứ tự so sánh diễn đạt đúng quan hệ đó. Việc tìm hàng xóm và giữ dữ liệu duy nhất chỉ đáng tin khi cả hai cùng dựa trên một mô hình nhất quán.
