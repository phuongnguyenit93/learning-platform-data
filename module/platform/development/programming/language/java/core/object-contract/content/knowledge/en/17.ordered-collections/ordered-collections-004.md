# Khác biệt kết quả giữa HashSet với TreeSet

## 1. Cùng là Set, vì sao kết quả có thể khác?

Trong Java, cả `HashSet<E>` và `TreeSet<E>` đều triển khai giao diện `Set<E>`: một tập hợp không chứa các phần tử được xem là trùng nhau. Tuy nhiên, chúng xác định phần tử “trùng” và tổ chức dữ liệu theo những cơ chế khác nhau.

- **`HashSet`** dựa vào `hashCode()` để xác định nhóm ứng viên và `equals(Object)` để nhận diện phần tử bằng nhau. Nó **không bảo đảm thứ tự duyệt**, dù trong một lần chạy bạn thấy phần tử tình cờ được in theo thứ tự nào đó.
- **`TreeSet`** là một `NavigableSet` có thứ tự, dùng **`compareTo()`** theo thứ tự tự nhiên hoặc **`Comparator.compare()`** được truyền vào. Hai phần tử được coi là cùng một phần tử của cây khi phép so sánh trả về **0**.

Vì thế, với một tập đầu vào giống nhau, hai set có thể khác **thứ tự duyệt**, khác **số phần tử**, khác kết quả `contains()` hoặc `remove()`, đặc biệt khi `compareTo`/`Comparator` không nhất quán với `equals`.

**Điểm cần nhớ:** Không thể kết luận “HashSet và TreeSet chỉ khác nhau ở chỗ TreeSet tự sắp xếp”. Cách nhận diện phần tử trùng nhau cũng là khác biệt mang tính hợp đồng.

## 2. So sánh nhanh hai cấu trúc

| Tiêu chí | `HashSet` | `TreeSet` |
| --- | --- | --- |
| Cơ chế tổ chức | Bảng băm, dựa trên `HashMap` | Cây tìm kiếm cân bằng, dựa trên `TreeMap` |
| Tiêu chí nhận diện trùng | Cùng tham chiếu hoặc bằng nhau theo `equals(Object)` trong cơ chế băm | `compareTo == 0` hoặc `Comparator.compare == 0` |
| Hợp đồng liên quan | `equals()` và `hashCode()` phải nhất quán | Thứ tự so sánh phải hợp lệ; nên nhất quán với `equals()` |
| Thứ tự duyệt | Không bảo đảm | Theo thứ tự tăng dần của natural ordering hoặc comparator |
| Thêm, tìm, xóa thông thường | Trung bình gần `O(1)` với băm phân bố tốt | `O(log n)` |
| Tìm phần tử gần nhất (`lower`, `floor`, `ceiling`, `higher`) | Không có API này trực tiếp | Có qua `NavigableSet` |
| `null` | Cho phép tối đa một phần tử `null` | Thứ tự tự nhiên thường không chấp nhận `null`; comparator riêng có thể quy định cách xử lý |
| Khi thích hợp | Cần kiểm tra tồn tại hoặc khử trùng theo equality, không cần thứ tự | Cần dữ liệu luôn theo thứ tự và các truy vấn khoảng, phần tử lân cận |

Các độ phức tạp trên là đánh giá thông thường, không phải cam kết mọi thao tác luôn mất đúng một lượng thời gian cố định. Hiệu năng thực tế còn phụ thuộc dữ liệu, số lần va chạm hash, chi phí tính hash, equality và comparator.

Nếu cần giữ **thứ tự chèn** chứ không phải thứ tự sắp xếp, hãy cân nhắc `LinkedHashSet`. Nó là một lựa chọn khác với `TreeSet`.

## 3. Trường hợp đơn giản: phần tử số nguyên có thứ tự tự nhiên

Với các `Integer` thông thường, `equals()` và `compareTo()` nhất quán: hai số nguyên có cùng giá trị thì bằng nhau theo cả hai cách. Vì vậy hai set sẽ khử trùng giống nhau, nhưng thứ tự duyệt có thể khác.

Tạo tệp `HashSetTreeSetDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class HashSetTreeSetDemo {
    public static void main(String[] args) {
        int[] numbers = {4, 1, 3, 2, 3};

        Set<Integer> hash = new HashSet<>();
        TreeSet<Integer> sorted = new TreeSet<>();

        for (int n : numbers) {
            hash.add(n);
            sorted.add(n);
        }

        System.out.println(hash.size());
        System.out.println(sorted.size());
        System.out.println(sorted);
        System.out.println(sorted.first());
        System.out.println(sorted.ceiling(3));
        System.out.println(sorted.higher(3));
        System.out.println(hash.contains(3));
        System.out.println(sorted.contains(3));

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        Set<BigDecimal> decimalHash = new HashSet<>();
        Set<BigDecimal> decimalTree = new TreeSet<>();

        decimalHash.add(a);
        decimalHash.add(b);
        decimalTree.add(a);
        decimalTree.add(b);

        System.out.println(decimalHash.size());
        System.out.println(decimalTree.size());
        System.out.println(
                decimalHash.contains(new BigDecimal("2.000")));
        System.out.println(
                decimalTree.contains(new BigDecimal("2.000")));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac HashSetTreeSetDemo.java
java HashSetTreeSetDemo
```

Kết quả:

```text
4
4
[1, 2, 3, 4]
1
3
4
true
true
2
1
false
true
```

Giải thích nửa đầu chương trình:

1. Dãy đầu vào có năm lần thêm, trong đó số `3` lặp hai lần. Cả hai set đều có kích thước **4**.
2. `sorted` in thành `[1, 2, 3, 4]` vì `TreeSet<Integer>` dùng thứ tự tăng dần của `Integer`.
3. `first()` trả phần tử nhỏ nhất `1`; `ceiling(3)` trả phần tử nhỏ nhất lớn hơn hoặc bằng 3, tức `3`; `higher(3)` trả phần tử nhỏ nhất lớn hơn 3, tức `4`.
4. Cả hai `contains(3)` đều trả `true`.

Ví dụ **cố ý không in trực tiếp `hash`**: thứ tự duyệt của `HashSet` không được Java bảo đảm. Ngay cả nếu tình cờ hiện ra `[1, 2, 3, 4]`, bạn cũng không được dựa vào đó trong chương trình.

Nửa sau chương trình minh họa khác biệt sâu hơn về **định nghĩa phần tử trùng**, không chỉ về thứ tự. Phần tiếp theo giải thích nguyên nhân.

## 4. BigDecimal: compareTo bằng 0 nhưng equals là false

`BigDecimal` lưu cả giá trị số học và **scale** (số chữ số thập phân theo cách biểu diễn nội bộ):

```java
BigDecimal a = new BigDecimal("2.0");  // scale = 1
BigDecimal b = new BigDecimal("2.00"); // scale = 2
```

Đoạn trên là minh họa và cần `import java.math.BigDecimal;`.

```text
a.compareTo(b) == 0  → true
a.equals(b)          → false
```

Lý do: `compareTo()` xét hai số bằng nhau về **giá trị toán học**, còn `BigDecimal.equals()` xét cả **giá trị và scale**.

Điều này tác động trực tiếp đến set:

- `HashSet<BigDecimal>` dùng equality theo `equals/hashCode`, nên hai phần tử `2.0` và `2.00` **khác nhau**: kích thước là **2**.
- `TreeSet<BigDecimal>` theo natural ordering dùng `compareTo == 0`, nên hai giá trị này được xem là **tương đương trong cây**: kích thước là **1**.
- `decimalHash.contains(new BigDecimal("2.000"))` là `false` vì scale 3 khác hai scale 1 và 2.
- `decimalTree.contains(new BigDecimal("2.000"))` là `true` vì giá trị số học bằng 2, so sánh với phần tử đã có trả 0.

`BigDecimal` là ví dụ tiêu biểu có **natural ordering inconsistent with equals**, được JavaDoc ghi nhận. Nó không phải lỗi của `HashSet` hoặc `TreeSet`: mỗi lớp đang thực hiện đúng cơ chế của mình.

Nếu nghiệp vụ xem `2.0`, `2.00` và `2` là **cùng một giá trị**, cần chọn rõ tiêu chí ở lớp xử lý dữ liệu. Nếu dùng `HashSet` và muốn khử trùng theo giá trị số học, có thể chuẩn hóa các `BigDecimal` bằng `stripTrailingZeros()` trước khi thêm và tra cứu. Tuy nhiên, phép chuẩn hóa có thể thay đổi scale, kể cả thành scale âm đối với số như `1000.00`; không áp dụng tùy tiện khi scale có ý nghĩa nghiệp vụ.

## 5. Comparator có thể khiến TreeSet “mất” phần tử khác nhau

Ngay cả khi kiểu phần tử có `equals` và natural ordering nhất quán, một `TreeSet` với **comparator do lập trình viên cung cấp** vẫn có thể coi những object khác nhau là trùng.

Ví dụ: mỗi học viên có một `id` và một `score`. Nếu comparator **chỉ** so điểm, hai học viên khác mã nhưng cùng điểm được so sánh bằng 0. `TreeSet` sẽ chỉ giữ một học viên đại diện cho nhóm điểm đó.

Tạo tệp `ComparatorSetDemo.java`:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorSetDemo {
    record Student(String id, int score) {}

    public static void main(String[] args) {
        Student a = new Student("S01", 90);
        Student b = new Student("S02", 90);

        System.out.println(a.equals(b));

        Set<Student> byEquality = new HashSet<>();
        byEquality.add(a);
        byEquality.add(b);
        System.out.println(byEquality.size());

        Comparator<Student> byScore =
                Comparator.comparingInt(Student::score);
        TreeSet<Student> byScoreOnly = new TreeSet<>(byScore);
        System.out.println(byScoreOnly.add(a));
        System.out.println(byScoreOnly.add(b));
        System.out.println(byScoreOnly.size());
        System.out.println(byScoreOnly.contains(b));

        Comparator<Student> byScoreThenId =
                Comparator.comparingInt(Student::score)
                        .thenComparing(Student::id);
        TreeSet<Student> fullOrder = new TreeSet<>(byScoreThenId);
        fullOrder.add(a);
        fullOrder.add(b);
        System.out.println(fullOrder.size());
        System.out.println(fullOrder.contains(b));
    }
}
```

Biên dịch và chạy:

```bash
javac ComparatorSetDemo.java
java ComparatorSetDemo
```

Kết quả:

```text
false
2
true
false
1
true
2
true
```

Phân tích:

- Record `Student` tự cung cấp `equals` và `hashCode` theo cả `id` lẫn `score`. `a.equals(b)` là `false`, nên `HashSet` chứa 2 học viên.
- `byScore.compare(a, b) == 0` vì cả hai đạt 90 điểm. `byScoreOnly.add(b)` trả `false` dù `b` khác `a` theo `equals`. `TreeSet` chỉ có 1 phần tử.
- `byScoreOnly.contains(b)` trả `true` vì đã có học viên **tương đương theo comparator**; nó không khẳng định chính đối tượng `b` đang được lưu.
- `byScoreThenId` phá hòa theo `id` sau `score`. Vì hai đối tượng khác mã, `fullOrder` chứa cả hai và vẫn giữ dữ liệu theo thứ tự điểm rồi mã.

**Quy tắc thiết kế:** Nếu mục tiêu là **sắp xếp theo điểm nhưng vẫn giữ mọi học viên**, comparator của `TreeSet` phải phá hòa bằng tiêu chí phân biệt đúng các đối tượng logic. Hoặc dùng một `List<Student>` rồi gọi `sort(byScore)` khi cần giữ nhiều học viên cùng điểm.

Dùng comparator chỉ theo điểm có thể hợp lý nếu **nghiệp vụ thật sự muốn tối đa một học viên cho mỗi mức điểm**, nhưng lúc ấy phải công bố rõ chính sách loại trùng.

## 6. Yêu cầu nhất quán giữa compareTo và equals

Với một lớp triển khai `Comparable<T>`, Java **khuyến nghị mạnh**:

```text
x.compareTo(y) == 0  ⇔  x.equals(y) == true
```

Với `TreeSet` dùng comparator, yêu cầu tương ứng là:

```text
comparator.compare(x, y) == 0  ⇔  x.equals(y) == true
```

Ở đây ký hiệu `⇔` nghĩa là điều kiện đúng theo **cả hai chiều**. Khi điều đó được bảo đảm:

1. Hai object bằng nhau theo `equals` không bị `TreeSet` coi là hai phần tử khác nhau.
2. Hai object khác nhau theo `equals` không bị `TreeSet` gộp do comparator trả 0.
3. `HashSet` và `TreeSet` có thể đồng thuận về tiêu chí phần tử trùng, dù cách sắp xếp và độ phức tạp khác nhau.

Một thứ tự **không nhất quán với equals** vẫn có thể tạo ra cây hoạt động theo thứ tự đã chỉ định, nhưng hành vi có thể không phù hợp với hợp đồng bình đẳng chung của `Set`. Đây là lý do tài liệu `TreeSet` đặc biệt lưu ý comparator hoặc natural ordering cần nhất quán với `equals` nếu muốn đáp ứng hợp đồng `Set` đầy đủ.

Cũng cần phân biệt **thứ tự so sánh hợp lệ** với **nhất quán cùng equals**. Một comparator phải có tính nhất quán, bắc cầu và dấu đối xứng theo các quy tắc của `Comparator`. Comparator sai các quy tắc đó còn gây vấn đề nghiêm trọng hơn chỉ lệch equality.

## 7. Null, khả năng so sánh và lỗi thường thấy khi thêm phần tử

`HashSet` cho phép **một phần tử `null`**. Thêm `null` lần hai không làm thay đổi kích thước set.

Với `TreeSet`, cây cần biết cách so sánh phần tử. Do đó:

- Khi dùng thứ tự tự nhiên như `TreeSet<String>` hoặc `TreeSet<Integer>`, thêm `null` sẽ gây `NullPointerException` trong triển khai tiêu chuẩn.
- Một comparator như `Comparator.nullsFirst(...)` có thể định nghĩa thứ tự cho `null` nếu nghiệp vụ cần; khi đó một `TreeSet` được tạo với comparator phù hợp có thể chứa `null`.
- Nếu các phần tử không có natural ordering tương thích, hoặc không so sánh được với nhau, `TreeSet` có thể ném `ClassCastException`. Ví dụ record `Student` ở trên không triển khai `Comparable`, nên phải dùng `new TreeSet<>(comparator)` nếu muốn chứa nhiều học viên.

Không được suy rằng `TreeSet` tự biết cách so sánh hai object tùy ý. Muốn `TreeSet` nhận dữ liệu, phải cung cấp **thứ tự tự nhiên** hoặc một **comparator** rõ ràng.

## 8. Thay đổi trạng thái object sau khi thêm vào set

Nếu object được sử dụng làm phần tử set mà các trường liên quan đến equality hoặc ordering có thể thay đổi, hành vi tìm kiếm có thể trở nên sai lệch:

- Trong `HashSet`, nếu `hashCode()`/ `equals()` thay đổi do sửa trường của phần tử sau khi chèn, việc `contains` hoặc `remove` có thể không tìm được đối tượng như kỳ vọng.
- Trong `TreeSet`, nếu tiêu chí `compareTo` hoặc `Comparator` thay đổi sau khi chèn, vị trí của phần tử trong cây có thể không còn phù hợp thứ tự; thao tác tìm, xóa hoặc duyệt có thể cho kết quả khó dự đoán.

Với khóa và phần tử được sử dụng lâu dài, nên **ưu tiên dữ liệu bất biến**. Nếu thật sự cần thay đổi tiêu chí định danh hoặc thứ tự, hãy xóa phần tử khỏi set **trước khi** sửa rồi thêm lại, hoặc tạo một object bất biến mới.

`Comparator` cũng cần dựa trên tiêu chí ổn định. Nếu nó phụ thuộc vào trạng thái bên ngoài thay đổi (ví dụ cấu hình động), cấu trúc cây có thể mất tính nhất quán ngay cả khi object không đổi.

## 9. Chọn HashSet hay TreeSet trong tình huống thực tế?

**Chọn `HashSet` khi:**

- Mục tiêu là kiểm tra tồn tại, loại trùng, thêm/xóa theo equality của đối tượng.
- Không cần thứ tự duyệt hay truy vấn phần tử gần nhất.
- Bạn muốn chi phí trung bình thấp cho các thao tác thông thường, với `equals/hashCode` hợp lệ và hash phân bố tốt.

**Chọn `TreeSet` khi:**

- Cần các phần tử **luôn có thứ tự** mà không phải sort lại mỗi lần truy cập.
- Cần `first`, `last`, `floor`, `ceiling`, `lower`, `higher`, `headSet`, `tailSet`, `subSet` hoặc truy vấn khoảng.
- Bạn có `Comparable` hoặc `Comparator` hợp lệ và hiểu rõ quan hệ `compare == 0` với `equals`.

**Chọn `LinkedHashSet` khi:** bạn cần tính duy nhất như set và **duy trì thứ tự thêm**. Nó không thay thế khả năng truy vấn theo giá trị thứ tự của `TreeSet`.

**Chọn `List` rồi sort khi:** bạn muốn giữ **mọi bản ghi**, kể cả các bản ghi cùng tiêu chí sắp xếp, và cần hiển thị theo một comparator. `TreeSet` là tập hợp, vì vậy `compare == 0` sẽ làm các phần tử bị coi là trùng.

Cả `HashSet` và `TreeSet` thông thường đều không tự bảo đảm an toàn khi nhiều luồng đồng thời sửa set; cần sử dụng cơ chế đồng bộ hoặc cấu trúc concurrent phù hợp theo yêu cầu.

## 10. Checklist kiểm thử hai set

1. **Kiểm tra hai object cùng giá trị logic:** `equals` và `hashCode` có nhất quán không? `compareTo` hoặc comparator có trả 0 không?
2. **Kiểm tra hai object khác giá trị logic:** comparator có tiêu chí phá hòa đủ để không gộp nhầm chúng không?
3. **Thử phần tử trùng và số lượng:** sau khi `add`, đối chiếu kết quả `boolean` và `size()` của mỗi set.
4. **Kiểm tra thứ tự:** chỉ kỳ vọng thứ tự từ `TreeSet` (hoặc `LinkedHashSet` theo thứ tự thêm); không viết kiểm thử giả định thứ tự duyệt `HashSet`.
5. **Kiểm tra contains/remove:** đặc biệt với các cặp `BigDecimal("2.0")` và `BigDecimal("2.00")`, hoặc comparator chỉ so một trường.
6. **Kiểm tra `null` và dữ liệu không so sánh được:** cân nhắc loại phần tử, natural ordering và chính sách comparator.
7. **Kiểm tra dữ liệu mutable:** giữ bất biến các trường tham gia equality và ordering khi object còn trong set.
8. **Kiểm tra mục tiêu nghiệp vụ:** cần tập phần tử duy nhất, tập phần tử có thứ tự, thứ tự chèn hay danh sách có thể chứa giá trị trùng?

**Tự kiểm tra:**

- Thêm `2.0` và `2.00` dạng `BigDecimal` vào `HashSet` và `TreeSet` theo thứ tự tự nhiên: kích thước lần lượt bao nhiêu? **2 và 1.**
- Hai `Student` khác `id` nhưng cùng `score`; `TreeSet` chỉ so `score` giữ bao nhiêu phần tử? **1.**
- `HashSet` in ra theo thứ tự tăng dần trong một lần chạy thì có bảo đảm lần sau vẫn vậy không? **Không.**
- Muốn giữ mọi bản ghi cùng điểm và chỉ sắp xếp để hiển thị, nên dùng gì? **Một `List` và `sort` hoặc comparator phù hợp với yêu cầu giữ đủ bản ghi.**

**Ghi nhớ:** `HashSet` nhận diện phần tử trùng bằng `equals/hashCode`, còn `TreeSet` dùng kết quả so sánh bằng 0. Vì vậy chúng không chỉ khác nhau ở thứ tự duyệt: **số lượng phần tử và kết quả tìm kiếm cũng có thể khác**, đặc biệt với `BigDecimal` hoặc comparator không nhất quán với `equals`.