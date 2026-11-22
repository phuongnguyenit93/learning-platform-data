# Mối liên hệ giữa `equals()`, `hashCode()`, `compareTo()` và `Comparator` trong Java

Khi làm việc với đối tượng Java, cần phân biệt rõ **bằng nhau về mặt logic**, **mã băm để tra cứu**, và **thứ tự sắp xếp**. Bốn cơ chế trên liên quan nhau nhưng phục vụ các mục đích khác nhau. Nắm được mối liên hệ này giúp tránh lỗi khi dùng `HashSet`, `HashMap`, `TreeSet`, `TreeMap` và khi sắp xếp danh sách.

## 1. Bốn cơ chế trả lời bốn câu hỏi

| Cơ chế | Chữ ký tiêu biểu | Câu hỏi được trả lời | Nơi thường sử dụng |
| --- | --- | --- | --- |
| `equals()` | `boolean equals(Object other)` | Hai đối tượng có **bằng nhau về mặt logic** không? | `HashSet`, `HashMap`, `List.contains()` |
| `hashCode()` | `int hashCode()` | Mã băm dùng để phân nhóm/tra cứu là gì? | `HashSet`, `HashMap` |
| `compareTo()` | `int compareTo(T other)` trong `Comparable<T>` | **Thứ tự tự nhiên** giữa hai phần tử là gì? | `TreeSet`, `TreeMap`, sắp xếp tự nhiên |
| `Comparator<T>` | `int compare(T a, T b)` | **Thứ tự tùy chỉnh** cho một tác vụ là gì? | `List.sort()`, `TreeSet`, `TreeMap`, `PriorityQueue` |

Mọi đối tượng đều thừa hưởng `equals()` và `hashCode()` từ `Object`. `compareTo()` chỉ hiện diện khi lớp triển khai `Comparable<T>`. `Comparator<T>` là một chiến lược so sánh độc lập, có thể tạo nhiều chiến lược cho cùng một lớp.

Ba mệnh đề dễ nhầm:

- `a.equals(b) == true` **bắt buộc kéo theo** `a.hashCode() == b.hashCode()`.
- `a.hashCode() == b.hashCode()` **không kéo theo** `a.equals(b)` vì có thể xảy ra va chạm hash.
- `a.compareTo(b) == 0` hay `comparator.compare(a,b) == 0` chỉ có nghĩa là **tương đương theo phép so sánh đó**; nó không nhất thiết bằng `equals()`.

## 2. Hợp đồng của `equals()` và `hashCode()`

### 2.1. `equals()` định nghĩa sự bằng nhau

Với các đối tượng không null `x`, `y`, `z`, một triển khai `equals()` đúng phải thỏa:

1. **Phản xạ:** `x.equals(x)` luôn `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` phải giống nhau.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Nhất quán:** khi trạng thái liên quan không đổi, kết quả so sánh phải ổn định.
5. **So với null:** `x.equals(null)` luôn `false`.

`Object.equals()` mặc định so sánh tham chiếu (`==`). Nếu nghiệp vụ coi hai đối tượng có cùng mã định danh là cùng thực thể, cần ghi đè `equals()` để biểu đạt điều đó.

### 2.2. `hashCode()` phải nhất quán với `equals()`

Hợp đồng quan trọng nhất: **hai đối tượng bằng nhau theo `equals()` phải có cùng mã băm**. Hash của cùng đối tượng phải ổn định khi những thông tin tham gia quan hệ bằng nhau không đổi, trong một lần thực thi.

Hai đối tượng khác nhau được phép có cùng hash; `hashCode()` không phải ID độc nhất. `HashMap`/`HashSet` dùng hash để định vị nhóm tra cứu, rồi dùng phép bằng nhau để phân biệt các khóa liên quan. Vì vậy chỉ kiểm tra `hashCode()` bằng nhau là chưa đủ.

Nếu `equals()` dựa trên `id`, thì `hashCode()` cũng nên dựa trên `id`. Ví dụ, hai `Student` cùng `id` nhưng khác `name` vẫn bằng nhau; tính hash từ cả `id` và `name` sẽ vi phạm hợp đồng. Quy tắc thực hành là **ghi đè `equals()` thì ghi đè cả `hashCode()`**, dùng cùng tập thuộc tính mang ý nghĩa bằng nhau.

Một lưu ý khác: không nên thay đổi thuộc tính tham gia `equals()`/`hashCode()` sau khi đối tượng đã được đưa vào `HashSet` hoặc dùng làm khóa `HashMap`. Nếu hash thay đổi, thao tác tìm hoặc xóa có thể thất bại. Ưu tiên khóa bất biến.

## 3. `Comparable` và `Comparator` quy định thứ tự

### 3.1. Ba nhóm kết quả

Với `a.compareTo(b)` hoặc `comparator.compare(a,b)`:

- Số **âm**: `a` đứng trước `b`.
- Số **0**: `a`, `b` tương đương theo thứ tự đó.
- Số **dương**: `a` đứng sau `b`.

Không được giả định kết quả chỉ là `-1`, `0`, `1`; cần kiểm tra dấu. Phép so sánh phải có tính nhất quán, phản đối xứng về dấu và bắc cầu. Nếu `compare(a,b)==0`, so sánh hai phần tử ấy với phần tử thứ ba phải có cùng dấu. Những quy tắc này giúp thuật toán sắp xếp và cấu trúc cây hoạt động đúng.

`Comparable<T>` nằm trong lớp để cung cấp **một thứ tự tự nhiên**, chẳng hạn sinh viên theo mã. `Comparator<T>` tách riêng chiến lược sắp xếp: theo điểm giảm dần, theo tên tăng dần, rồi theo ID để phân biệt.

Ví dụ (giả sử có kiểu `Student` với phương thức `score()` và `id()` như phần 5):

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score).reversed();

Comparator<Student> byScoreThenId =
        Comparator.comparingInt(Student::score)
                  .reversed()
                  .thenComparing(Student::id);
```

`thenComparing()` chỉ áp dụng tiêu chí phụ khi tiêu chí đầu cho kết quả `0`. Với thuộc tính cho phép null, cân nhắc `Comparator.nullsFirst(...)` hoặc `Comparator.nullsLast(...)` để chỉ rõ chính sách. Hàm so sánh không nên thay đổi theo thời gian hoặc dựa vào trạng thái đang biến đổi trong khi đối tượng nằm trong tập có thứ tự.

**Lỗi phổ biến: so sánh số nguyên bằng phép trừ.**

```java
// Có thể tràn int khi hai giá trị cách nhau quá lớn:
Comparator<Integer> bad = (a, b) -> a - b;

// An toàn hơn:
Comparator<Integer> good = Integer::compare;
```

Với trường số thực, phải xét chính sách xử lý `NaN`, `-0.0`, `+0.0` phù hợp ngữ nghĩa, thay vì tự viết phép trừ rồi ép sang `int`.

### 3.2. Nhất quán với `equals()` là gì?

Một thứ tự được gọi là **nhất quán với `equals()`** nếu với mọi `a`, `b`:

```java
a.compareTo(b) == 0  // khi và chỉ khi
a.equals(b)
```

Đây là **khuyến nghị rất quan trọng**, đặc biệt khi sử dụng `TreeSet`/`TreeMap`, nhưng không phải mọi kiểu `Comparable` bắt buộc tuân theo. `Comparator` dùng cho một ngữ cảnh cụ thể cũng có thể cố ý phân nhóm khác định nghĩa bằng nhau. Khi đó phải hiểu hệ quả đối với collection có thứ tự.

## 4. Quan hệ với các Java collection

| Cấu trúc/thao tác | Dùng cơ chế nào? | Cách xác định trùng lặp |
| --- | --- | --- |
| `HashSet<E>` | `hashCode()` và `equals()` | Theo `equals()` |
| `HashMap<K,V>` | `hashCode()` và `equals()` của khóa | Khóa tương đương theo `equals()` |
| `TreeSet<E>` | `compareTo()` hoặc `Comparator` | Phép so sánh trả `0` |
| `TreeMap<K,V>` | `compareTo()` hoặc `Comparator` của khóa | Phép so sánh khóa trả `0` |
| `List.sort(comparator)` | `Comparator` | Chỉ sắp xếp, **không xóa** phần tử trùng |
| `Collections.sort(list)` | `Comparable` tự nhiên | Chỉ sắp xếp, **không xóa** phần tử trùng |
| `PriorityQueue` | `Comparable`/`Comparator` | Điều khiển thứ tự ưu tiên, **không tự khử trùng** |

`TreeSet` và `TreeMap` dùng so sánh thứ tự làm quan hệ tương đương cho phần tử/khóa. Do đó:

- Nếu `!a.equals(b)` nhưng `compare(a,b)==0`, `HashSet` có thể giữ cả hai, còn `TreeSet` chỉ giữ một.
- Nếu `a.equals(b)` nhưng `compare(a,b)!=0`, `HashSet` chỉ giữ một, còn `TreeSet` có thể giữ cả hai.

Trường hợp thứ hai khiến tính duy nhất trong `TreeSet` không khớp định nghĩa `Set` dựa trên `equals()`; đây là lý do nên dùng phép so sánh nhất quán với `equals()` khi cần ngữ nghĩa tập hợp thông thường. `TreeMap` có rủi ro tương tự với khóa: lần `put()` thứ hai có thể thay giá trị một khóa so sánh bằng `0`, dù `equals()` của hai đối tượng khóa là `false`.

Không dùng `HashSet` nếu yêu cầu chính là sắp xếp; không dùng `TreeSet` chỉ để xếp danh sách theo điểm nếu cần giữ đủ các bản ghi cùng điểm.

## 5. Ví dụ Java 17+ chạy được: định danh theo ID, sắp theo điểm

Giả sử `Student` có `id`, `name`, `score`; quy tắc nghiệp vụ là **cùng `id` nghĩa là cùng sinh viên** dù tên hay điểm khác nhau. Vì thế `equals()`, `hashCode()` và thứ tự tự nhiên cùng dựa trên `id`. Một `Comparator` khác xếp sinh viên theo điểm giảm dần để phục vụ giao diện.

Tạo file **`ObjectContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;

record Student(String id, String name, int score)
        implements Comparable<Student> {

    Student {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof Student other
                && id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }

    @Override
    public int compareTo(Student other) {
        return id.compareTo(other.id);
    }
}

public class ObjectContractDemo {
    public static void main(String[] args) {
        Student a = new Student("S01", "Lan", 90);
        Student b = new Student("S01", "Lan cập nhật", 75);
        Student c = new Student("S02", "Minh", 95);

        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("compareTo: " + a.compareTo(b));

        System.out.println("HashSet: "
                + new HashSet<>(List.of(a, b, c)).size());
        System.out.println("TreeSet natural: "
                + new TreeSet<>(List.of(a, b, c)).size());

        Comparator<Student> byScoreThenId =
                Comparator.comparingInt(Student::score)
                          .reversed()
                          .thenComparing(Student::id);

        List<Student> sorted =
                new ArrayList<>(List.of(a, b, c));
        sorted.sort(byScoreThenId);
        System.out.println("Sorted: "
                + sorted.stream()
                        .map(s -> s.id() + ":" + s.score())
                        .toList());

        TreeSet<Student> scoreSet = new TreeSet<>(byScoreThenId);
        scoreSet.addAll(List.of(a, b, c));
        System.out.println("TreeSet by score: "
                + scoreSet.size());
    }
}
```

Biên dịch và chạy:

```bash
javac ObjectContractDemo.java
java ObjectContractDemo
```

Kết quả chính xác:

```text
equals: true
same hash: true
compareTo: 0
HashSet: 2
TreeSet natural: 2
Sorted: [S02:95, S01:90, S01:75]
TreeSet by score: 3
```

**Giải thích:**

1. `a` và `b` cùng mã `S01` nên `equals()` đúng, hash bằng nhau và `compareTo()` trả `0`.
2. `HashSet` chỉ giữ hai ID phân biệt; `TreeSet` với thứ tự tự nhiên theo ID cũng giữ hai.
3. `List.sort(byScoreThenId)` sắp `95, 90, 75` nhưng **giữ cả ba** bản ghi.
4. `TreeSet` với comparator theo điểm rồi ID giữ cả ba: `a` và `b` có điểm khác nhau nên comparator không trả `0` dù `equals()` coi chúng bằng nhau. Đây là ví dụ chủ ý về comparator **không nhất quán với `equals()`**.

Record mặc định tự tạo `equals()` và `hashCode()` từ **toàn bộ các component**. Ở đây ghi đè cả hai để thể hiện quy tắc ID là danh tính nghiệp vụ. `compareTo()` cũng dùng ID để thứ tự tự nhiên nhất quán với định nghĩa ấy. Với một *value object* thuần túy, cách đúng có thể là giữ `equals()`/`hashCode()` mặc định của record để xét tất cả thành phần; không phải kiểu nào cũng nên định danh theo ID.

## 6. Trường hợp đặc biệt có thật: `BigDecimal`

`BigDecimal("2.0")` và `BigDecimal("2.00")` có cùng giá trị số học, nên `compareTo()` trả `0`. Nhưng `equals()` còn xét *scale*, nên trả `false`. Đây là ví dụ nổi tiếng cho thứ tự tự nhiên **không nhất quán với `equals()`**.

Tạo file **`BigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println(x.equals(y));
        System.out.println(x.compareTo(y));
        System.out.println(new HashSet<>(List.of(x, y)).size());
        System.out.println(new TreeSet<>(List.of(x, y)).size());
    }
}
```

Chạy:

```bash
javac BigDecimalDemo.java
java BigDecimalDemo
```

Kết quả:

```text
false
0
2
1
```

`HashSet` coi chúng là hai giá trị theo `equals()`, trong khi `TreeSet` coi chúng tương đương theo thứ tự tự nhiên và chỉ giữ một. Khi xử lý số tiền hoặc lượng đo, cần quyết định ứng dụng đòi hỏi cùng **giá trị số học** hay cùng **giá trị và scale** trước khi chọn cách chuẩn hóa/so sánh.

## 7. Quy trình thiết kế cho một kiểu đối tượng

**Bước 1 — Định nghĩa “bằng nhau”.** Chọn những thuộc tính tạo danh tính logic. Với một thực thể, đó có thể là ID ổn định; với value object, đó thường là các thuộc tính giá trị. Tránh quan hệ bằng nhau phụ thuộc thuộc tính có thể thay đổi khi dùng làm khóa.

**Bước 2 — Triển khai `equals()` và `hashCode()` như một cặp.** Cùng dùng những thuộc tính đã chọn. Có thể nhờ IDE sinh code, dùng `Objects.equals()` để xử lý null và `Objects.hash()` khi cần gộp nhiều trường; chú ý chi phí tạo mảng của `Objects.hash()` trong đường chạy nhạy hiệu năng.

**Bước 3 — Chọn thứ tự tự nhiên nếu có ý nghĩa.** Triển khai `Comparable<T>` khi có một trật tự mặc định rõ ràng; cố gắng giữ `compareTo()==0` tương ứng `equals()`. Không cần ép mọi kiểu triển khai `Comparable`.

**Bước 4 — Dùng `Comparator` cho từng nhu cầu khác nhau.** Ví dụ theo tên, điểm, ngày tạo; kết hợp `thenComparing()` nếu cần tiêu chí phụ. Với tập/cây có thứ tự, xác định rõ comparator quyết định tính duy nhất như thế nào.

**Bước 5 — Chọn đúng cấu trúc dữ liệu.** `HashMap`/`HashSet` cho tra cứu, khử trùng theo quan hệ bằng nhau; `TreeMap`/`TreeSet` khi cần thứ tự, truy vấn dải và quy tắc so sánh phù hợp; `List.sort()` để sắp xếp mà giữ tất cả bản ghi.

## 8. Lỗi thường gặp và checklist kiểm tra

- **Ghi đè `equals()` nhưng không ghi đè `hashCode()`:** hai đối tượng bằng nhau có thể không tìm thấy nhau trong cấu trúc dựa trên hash.
- **Tính hash bằng trường không tham gia `equals()`:** vi phạm hợp đồng khi hai đối tượng bằng nhau mà hash khác nhau.
- **Sửa dữ liệu khóa sau khi đưa vào `HashSet`/`HashMap`:** nguy cơ không tra cứu/xóa được khóa theo trạng thái mới.
- **Nghĩ `compareTo()==0` luôn đồng nghĩa `equals()`:** sai với `BigDecimal` và nhiều comparator tùy chỉnh.
- **Cho rằng `TreeSet` chỉ sắp xếp:** thực tế phép so sánh còn quyết định hai phần tử có được giữ đồng thời hay không.
- **Comparator chỉ xét điểm/tên mà thiếu tiêu chí phân biệt:** các phần tử cùng điểm/tên có thể bị `TreeSet` gộp; cần xét quy tắc nghiệp vụ và tiêu chí phụ.
- **Dùng `a - b` để so sánh `int`:** có nguy cơ tràn số, hãy dùng `Integer.compare(...)` hoặc `Comparator.comparingInt(...)`.
- **Cho `equals()` giữa lớp cha và lớp con sai ngữ nghĩa:** dễ phá đối xứng/bắc cầu; cân nhắc `final`, `record` hoặc thiết kế mô hình giá trị đơn giản và kiểm thử.
- **Nhầm hash với định danh duy nhất:** mã băm được phép va chạm; tính đúng đắn đến từ hợp đồng của hai phương thức.
- **Chỉ thử trên dữ liệu “đẹp”:** hãy thử cùng ID khác thuộc tính, cùng điểm khác ID, trường null nếu hợp lệ, số cực trị và các collection khác nhau.

**Ghi nhớ:** `equals()` định nghĩa bằng nhau; `hashCode()` phải tương thích với định nghĩa đó; `compareTo()` cho thứ tự tự nhiên; `Comparator` cho thứ tự theo ngữ cảnh. Quan hệ thứ tự và quan hệ bằng nhau nên nhất quán khi khả thi, đặc biệt nếu dùng để xác định phần tử duy nhất trong `TreeSet` hoặc khóa trong `TreeMap`.
