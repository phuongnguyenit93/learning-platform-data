# Đảo toàn bộ Comparator hoặc chỉ đảo một tiêu chí — Java 8+

> Chủ đề **Comparator**. Bài này giải thích chính xác phạm vi của `Comparator.reversed()` trong chuỗi `thenComparing`, cách đảo riêng tiêu chí chính/phụ, xử lý tie-breaker và null. Những API được trình bày đều có từ Java 8, vẫn áp dụng trên các JDK hiện đại. Ví dụ có thể biên dịch bằng JDK 17+ với `--release 8`.

## 1. Kết quả học tập

Sau bài này bạn sẽ biết:

- Phân biệt `Comparator.reversed()` (đảo **comparator hiện tại**) với `Comparator.reverseOrder()` (comparator đảo **thứ tự tự nhiên**).
- Đọc thứ tự ưu tiên các tiêu chí trong `comparing(...).thenComparing(...)`.
- Đảo **toàn bộ** một comparator ghép nhiều tiêu chí, hoặc chỉ đảo một tiêu chí trong chuỗi.
- Phân biệt đảo comparator với đảo thứ tự phần tử của List.
- Giữ đúng quy tắc `nullsFirst`/`nullsLast` khi chỉ muốn đổi chiều giá trị.
- Tránh lỗi tràn số, lỗi thiếu tie-breaker, sai hợp đồng comparator và mất dữ liệu trong `TreeSet`.

## 2. Comparator quyết định thứ tự như thế nào?

`Comparator<T>` là functional interface với phương thức chính:

```java
int compare(T left, T right);
```

| Kết quả | Ý nghĩa |
| --- | --- |
| Số âm | `left` đứng trước `right` |
| `0` | Bằng nhau **theo comparator** |
| Số dương | `left` đứng sau `right` |

Không được mặc định `compare` chỉ trả -1, 0 và 1; chỉ **dấu** của kết quả là quan trọng. Một comparator hợp lệ phải có quan hệ so sánh nhất quán, có tính bắc cầu và thỏa các quy tắc tương ứng của JavaDoc.

```java
Comparator<Integer> increasing = Integer::compare;
Comparator<Integer> decreasing = increasing.reversed();
```

`reversed()` tạo **một comparator mới với quan hệ thứ tự ngược**. Nó không sửa comparator ban đầu, không tự sắp xếp danh sách và không thay đổi dữ liệu.

`Comparator.reverseOrder()` là một static factory tạo comparator đảo thứ tự tự nhiên cho kiểu `Comparable`:

```java
Comparator<String> wordsDescending = Comparator.reverseOrder();
```

Chọn `reversed()` khi đã có comparator cụ thể; dùng `reverseOrder()` cho giá trị có natural order phù hợp (như String, Integer). Natural order/reverseOrder trực tiếp có thể ném `NullPointerException` khi gặp null.

## 3. Chuỗi nhiều tiêu chí: `thenComparing` chỉ chạy khi hòa

Ví dụ phải sắp xếp nhân viên theo:

1. `department` — tên phòng ban;
2. `score` — điểm đánh giá;
3. `name` — tên nhân viên.

```java
Comparator<Staff> allAscending = Comparator
        .comparing(Staff::department)
        .thenComparingInt(Staff::score)
        .thenComparing(Staff::name);
```

`thenComparing` dùng tiêu chí sau **chỉ khi** tiêu chí trước có kết quả bằng `0`.

```text
So sánh phòng ban
     |-- khác nhau --> quyết định ngay
     |
     |-- bằng nhau --> so sánh điểm
                           |-- khác nhau --> quyết định
                           |
                           |-- bằng nhau --> so sánh tên
```

Một chuỗi `A.thenComparing(B).thenComparing(C)` có thứ tự ưu tiên A → B → C. Thứ tự các lời gọi này không được thay thế tùy ý.

## 4. Khác biệt quan trọng nhất: vị trí của `reversed()`

Giả sử A là comparator phòng ban tăng dần, B là comparator điểm tăng dần, C là comparator tên tăng dần.

| Cách ghép | Ý nghĩa |
| --- | --- |
| `A.thenComparing(B).thenComparing(C)` | A tăng, B tăng, C tăng |
| `A.thenComparing(B).thenComparing(C).reversed()` | **A giảm, B giảm, C giảm** |
| `A.reversed().thenComparing(B).thenComparing(C)` | **A giảm**, B tăng, C tăng |
| `A.thenComparing(B.reversed()).thenComparing(C)` | A tăng, **B giảm**, C tăng |
| `A.thenComparing(B).thenComparing(C.reversed())` | A tăng, B tăng, **C giảm** |

Vì sao? `reversed()` là phương thức được gọi trên **một đối tượng comparator đã xây xong tới thời điểm đó**.

```java
// Đảo CẢ PHÒNG BAN, ĐIỂM VÀ TÊN:
Comparator<Staff> wholeReverse = Comparator
        .comparing(Staff::department)
        .thenComparingInt(Staff::score)
        .thenComparing(Staff::name)
        .reversed();
```

Lệnh ở cuối đảo **kết quả so sánh của toàn bộ chuỗi**, chứ không chỉ tên.

Ngược lại:

```java
// Phòng ban TĂNG, điểm GIẢM, tên TĂNG:
Comparator<Staff> scoreOnlyReverse = Comparator
        .comparing(Staff::department)
        .thenComparing(
                Comparator.comparingInt(Staff::score).reversed())
        .thenComparing(Staff::name);
```

Ở đây `reversed()` chỉ áp dụng cho `Comparator.comparingInt(Staff::score)`; comparator của phòng ban và tên không đổi chiều.

### Đặt tên comparator con để tránh nhầm

```java
Comparator<Staff> departmentAsc =
        Comparator.comparing(Staff::department);
Comparator<Staff> scoreDesc =
        Comparator.comparingInt(Staff::score).reversed();
Comparator<Staff> nameAsc =
        Comparator.comparing(Staff::name);

Comparator<Staff> businessOrder = departmentAsc
        .thenComparing(scoreDesc)
        .thenComparing(nameAsc);
```

Đây là kiểu viết dễ bảo trì khi nghiệp vụ yêu cầu thay đổi **một** chiều sắp xếp nhưng giữ nguyên các tiêu chí khác.

## 5. Ba tình huống thường gặp

### 5.1. Đảo mọi tiêu chí cùng lúc

```java
Comparator<Staff> ascending = Comparator
        .comparing(Staff::department)
        .thenComparingInt(Staff::score)
        .thenComparing(Staff::name);

Comparator<Staff> descendingAll = ascending.reversed();
```

Nếu ascending quy định `department ASC, score ASC, name ASC` thì descendingAll quy định `department DESC, score DESC, name DESC`.

### 5.2. Đảo riêng tiêu chí chính

```java
Comparator<Staff> departmentDesc = Comparator
        .comparing(Staff::department)
        .reversed()
        .thenComparingInt(Staff::score)
        .thenComparing(Staff::name);
// department DESC, score ASC, name ASC.
```

Chú ý `reversed` ở **trước** `thenComparingInt`.

### 5.3. Đảo riêng tiêu chí phụ

```java
Comparator<Staff> scoreDesc = Comparator
        .comparing(Staff::department)
        .thenComparing(
                Comparator.comparingInt(Staff::score).reversed())
        .thenComparing(Staff::name);
// department ASC, score DESC, name ASC.
```

Muốn đảo tên mà giữ hai trường trước:

```java
Comparator<Staff> nameDesc = Comparator
        .comparing(Staff::department)
        .thenComparingInt(Staff::score)
        .thenComparing(
                Comparator.comparing(Staff::name).reversed());
// department ASC, score ASC, name DESC.
```

Một lựa chọn tương đương cho một khóa String là `Comparator.comparing(Staff::name, Comparator.reverseOrder())`. Chú ý kiểu này khác gọi `reversed` ở cuối một chuỗi đã gồm ba khóa.

## 6. Bảng dữ liệu minh họa

| Department | Name | Score |
| --- | --- | ---: |
| Sales | Mai | 90 |
| Sales | An | 90 |
| Sales | Binh | 70 |
| Tech | Chi | 95 |
| Tech | Lan | 95 |
| Tech | Hoa | 80 |

Nếu dùng `department ASC, score ASC, name ASC`, thứ tự sẽ là:

```text
Sales/Binh:70
Sales/An:90
Sales/Mai:90
Tech/Hoa:80
Tech/Chi:95
Tech/Lan:95
```

Nếu gọi `reversed()` trên toàn bộ comparator:

```text
Tech/Lan:95
Tech/Chi:95
Tech/Hoa:80
Sales/Mai:90
Sales/An:90
Sales/Binh:70
```

Nếu chỉ đảo `score` (phòng ban và tên vẫn tăng):

```text
Sales/An:90
Sales/Mai:90
Sales/Binh:70
Tech/Chi:95
Tech/Lan:95
Tech/Hoa:80
```

Nếu chỉ đảo `name` (phòng ban và điểm vẫn tăng):

```text
Sales/Binh:70
Sales/Mai:90
Sales/An:90
Tech/Hoa:80
Tech/Lan:95
Tech/Chi:95
```

Bạn có thể đọc từng nhóm để tự kiểm tra. Với điểm bằng nhau, tên quyết định thứ tự. Khi đảo toàn bộ comparator, **thứ tự của các tie theo tên cũng bị đảo**.

## 7. Chương trình Java hoàn chỉnh và kết quả kiểm chứng

Chương trình sau tạo bốn comparator trên cùng dữ liệu và xử lý một lỗi thực tế khác: khi đảo toàn bộ comparator có `nullsLast`, null có thể chuyển lên đầu.

Lưu vào file **`ComparatorDirectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ComparatorDirectionDemo {
    static final class Staff {
        private final String department;
        private final String name;
        private final int score;

        Staff(String department, String name, int score) {
            this.department = department;
            this.name = name;
            this.score = score;
        }

        String department() { return department; }
        String name() { return name; }
        int score() { return score; }

        @Override public String toString() {
            return department + "/" + name + ":" + score;
        }
    }

    static String sortedNames(List<Staff> source, Comparator<Staff> comparator) {
        return source.stream().sorted(comparator)
                .map(Staff::toString)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Staff> staff = Arrays.asList(
                new Staff("Sales", "Mai", 90),
                new Staff("Sales", "An", 90),
                new Staff("Sales", "Binh", 70),
                new Staff("Tech", "Chi", 95),
                new Staff("Tech", "Lan", 95),
                new Staff("Tech", "Hoa", 80));

        Comparator<Staff> allAsc = Comparator
                .comparing(Staff::department)
                .thenComparingInt(Staff::score)
                .thenComparing(Staff::name);

        Comparator<Staff> allDesc = allAsc.reversed();

        Comparator<Staff> scoreDescOnly = Comparator
                .comparing(Staff::department)
                .thenComparing(Comparator.comparingInt(Staff::score).reversed())
                .thenComparing(Staff::name);

        Comparator<Staff> nameDescOnly = Comparator
                .comparing(Staff::department)
                .thenComparingInt(Staff::score)
                .thenComparing(Comparator.comparing(Staff::name).reversed());

        List<String> words = Arrays.asList("z", null, "a");
        Comparator<String> nullLastAsc =
                Comparator.nullsLast(Comparator.naturalOrder());

        List<String> ascWords = new ArrayList<>(words);
        List<String> wholeReverseWords = new ArrayList<>(words);
        List<String> valuesReverseWords = new ArrayList<>(words);
        ascWords.sort(nullLastAsc);
        wholeReverseWords.sort(nullLastAsc.reversed());
        valuesReverseWords.sort(
                Comparator.nullsLast(Comparator.reverseOrder()));

        String allAscResult = sortedNames(staff, allAsc);
        String allDescResult = sortedNames(staff, allDesc);
        String scoreDescResult = sortedNames(staff, scoreDescOnly);
        String nameDescResult = sortedNames(staff, nameDescOnly);

        System.out.println("All ascending: " + allAscResult);
        System.out.println("Whole reversed: " + allDescResult);
        System.out.println("Only score descending: " + scoreDescResult);
        System.out.println("Only name descending: " + nameDescResult);
        System.out.println("Null last, values ascending: " + ascWords);
        System.out.println("Whole reversed, null first: " + wholeReverseWords);
        System.out.println("Values reversed, null still last: " + valuesReverseWords);

        if (!allAscResult.equals("Sales/Binh:70, Sales/An:90, Sales/Mai:90, Tech/Hoa:80, Tech/Chi:95, Tech/Lan:95")
                || !allDescResult.equals("Tech/Lan:95, Tech/Chi:95, Tech/Hoa:80, Sales/Mai:90, Sales/An:90, Sales/Binh:70")
                || !scoreDescResult.equals("Sales/An:90, Sales/Mai:90, Sales/Binh:70, Tech/Chi:95, Tech/Lan:95, Tech/Hoa:80")
                || !nameDescResult.equals("Sales/Binh:70, Sales/Mai:90, Sales/An:90, Tech/Hoa:80, Tech/Lan:95, Tech/Chi:95")
                || !ascWords.equals(Arrays.asList("a", "z", null))
                || !wholeReverseWords.equals(Arrays.asList(null, "z", "a"))
                || !valuesReverseWords.equals(Arrays.asList("z", "a", null))) {
            throw new AssertionError("Unexpected sort results");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch với JDK 17+ và xác nhận khả năng tương thích Java 8:

```bash
javac --release 8 ComparatorDirectionDemo.java
java ComparatorDirectionDemo
```

Stdout đã chạy và kiểm chứng trên OpenJDK 24:

```text
All ascending: Sales/Binh:70, Sales/An:90, Sales/Mai:90, Tech/Hoa:80, Tech/Chi:95, Tech/Lan:95
Whole reversed: Tech/Lan:95, Tech/Chi:95, Tech/Hoa:80, Sales/Mai:90, Sales/An:90, Sales/Binh:70
Only score descending: Sales/An:90, Sales/Mai:90, Sales/Binh:70, Tech/Chi:95, Tech/Lan:95, Tech/Hoa:80
Only name descending: Sales/Binh:70, Sales/Mai:90, Sales/An:90, Tech/Hoa:80, Tech/Lan:95, Tech/Chi:95
Null last, values ascending: [a, z, null]
Whole reversed, null first: [null, z, a]
Values reversed, null still last: [z, a, null]
Checks passed.
```

`source.stream().sorted(comparator)` không sắp xếp trực tiếp lại `source`; đây là intermediate operation tạo một luồng đã sắp. Nếu muốn chỉnh thứ tự của danh sách hỗ trợ mutation tại chỗ, dùng `list.sort(comparator)`. Trong ví dụ, mỗi lần sort dùng một stream mới; stream đã chạy terminal không được tái sử dụng.

## 8. Bẫy `nullsLast`: đảo toàn bộ làm đổi cả vị trí null

Giả sử yêu cầu **giá trị giảm dần, nhưng null phải đứng cuối**.

Cách viết này **không đáp ứng yêu cầu**:

```java
Comparator<String> nullLastAsc =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> wrong =
        nullLastAsc.reversed();
```

Vì `nullLastAsc` coi null đứng sau các giá trị bình thường, đảo cả comparator khiến null **đứng trước**:

```text
[a, z, null]    // nullsLast(naturalOrder)
[null, z, a]    // nullsLast(naturalOrder).reversed()
```

Để chỉ đảo các giá trị non-null mà vẫn giữ null cuối, đặt `reverseOrder()` **bên trong** `nullsLast`:

```java
Comparator<String> right =
        Comparator.nullsLast(Comparator.reverseOrder());
// [z, a, null]
```

So sánh:

| Comparator | Null | Giá trị không null |
| --- | --- | --- |
| `nullsLast(naturalOrder())` | Cuối | Tăng dần |
| `nullsLast(naturalOrder()).reversed()` | **Đầu** | Giảm dần |
| `nullsLast(reverseOrder())` | **Cuối** | Giảm dần |
| `nullsFirst(reverseOrder())` | **Đầu** | Giảm dần |

**Phân biệt null object và null field:** Đối với object `Staff` có thể null, bao comparator đối tượng bằng `Comparator.nullsLast(...)`. Đối với field `name()` có thể null, đặt `nullsLast` tại comparator khóa:

```java
Comparator<Staff> byNullableNameDesc = Comparator.comparing(
        Staff::name,
        Comparator.nullsLast(Comparator.reverseOrder()));

// Chỉ khi cả Staff object cũng có thể null mới cần lớp bao:
Comparator<Staff> byNullableStaffAndName = Comparator.nullsLast(
        Comparator.comparing(
                Staff::name,
                Comparator.nullsLast(Comparator.reverseOrder())));
```

Không mặc định `Comparator.reverseOrder()` hoặc `naturalOrder()` tự chấp nhận null.

## 9. `Comparator.reversed` khác `Collections.reverse(List)`

`Comparator.reversed()` đảo **quan hệ so sánh**. `Collections.reverse(list)` chỉ đảo **vị trí hiện tại** của từng phần tử, hoàn toàn không biết comparator nào đã được dùng.

Ví dụ nguồn `[A(score=90), B(score=90), C(score=70)]`:

| Thao tác | Kết quả |
| --- | --- |
| Sort score tăng dần, **stable** | `[C,A,B]` |
| Sau đó `Collections.reverse(list)` | `[B,A,C]` |
| Sort score giảm dần, **stable** từ nguồn ban đầu | `[A,B,C]` |

Tại sao kết quả khác? `List.sort` theo JavaDoc là **stable sort**: với hai phần tử có `compare(a,b)==0`, thứ tự tương đối của chúng được giữ. Trong ví dụ, A và B cùng score nên vẫn A trước B khi sort trực tiếp từ nguồn ban đầu. `Collections.reverse` đơn giản đảo toàn bộ vị trí A/B.

Nếu yêu cầu là **đổi chiều của quy tắc sắp xếp**, hãy dùng comparator theo đúng chiều. Chỉ dùng `Collections.reverse` khi yêu cầu thực sự là lật vị trí của toàn bộ danh sách.

## 10. Tie-breaker và tính xác định

`thenComparing` chỉ xét tiêu chí tiếp theo khi tiêu chí trước trả `0`:

```java
Comparator<Staff> scoreDescThenNameAsc =
        Comparator.comparingInt(Staff::score)
                .reversed()
                .thenComparing(Staff::name);
```

Nếu hai nhân viên có điểm khác nhau, tên không quyết định thứ tự. Nếu cùng điểm, tên là tie-breaker.

Khi hai bản ghi giống nhau theo **tất cả** các tiêu chí, comparator trả `0`. `List.sort` giữ thứ tự tương đối theo đầu vào. Nhưng `TreeSet` và `TreeMap` dùng comparator để xác định những phần tử/key tương đương. Nếu comparator chỉ so sánh `score`, hai nhân viên khác nhau cùng score có thể bị coi là trùng trong `TreeSet`.

```java
Comparator<Staff> byScoreOnly = Comparator.comparingInt(Staff::score);
Set<Staff> ranked = new TreeSet<>(byScoreOnly);
// Các Staff cùng score có thể không được lưu thành phần tử tách biệt.
```

Đoạn mã trên chỉ minh họa, cần đặt trong file có import `Set`, `TreeSet` và lớp `Staff`. Nếu nghiệp vụ cần giữ tất cả bản ghi trong `TreeSet`, hãy thêm tiêu chí ID duy nhất, bất biến:

```java
Comparator<Employee> fullOrder = Comparator
        .comparing(Employee::department)
        .thenComparing(Comparator.comparingInt(Employee::score).reversed())
        .thenComparing(Employee::name)
        .thenComparingLong(Employee::id);
```

Đây là snippet minh họa với lớp `Employee` giả định có method getter tương ứng. `compare==0` khác với `equals==true` nếu chính sách so sánh không đồng nhất với nhận dạng object. Đảo comparator không tự giải quyết vấn đề trùng khóa.

## 11. Tránh phép trừ khi so sánh số nguyên

Đây là một lỗi không nên áp dụng:

```java
Comparator<Integer> bad = (a, b) -> b - a;
```

Phép trừ có thể tràn `int` khi dữ liệu gần `Integer.MIN_VALUE`/`MAX_VALUE`, làm sai dấu so sánh và vi phạm tính bắc cầu/đối xứng theo dấu.

Thay bằng:

```java
Comparator<Integer> safe = (a, b) -> Integer.compare(b, a);

// Hoặc:
Comparator<Integer> safe2 = Comparator.reverseOrder();
```

Khi sắp field primitive:

```java
Comparator<Staff> byScoreDesc =
        Comparator.comparingInt(Staff::score).reversed();
```

`comparingInt` sử dụng `ToIntFunction`, tránh việc trích xuất `Integer` boxed tại API so sánh. Với `long` dùng `Long.compare` hoặc `comparingLong`; với `double` dùng `Double.compare`/`comparingDouble` để xử lý đúng cả NaN và signed zero theo quy tắc Java. Không tạo comparator không ổn định bằng cách đọc/mutate trạng thái đang thay đổi trong `compare`.

## 12. Thứ tự trong các API khác

- **`List.sort(comparator)`:** sắp xếp List hiện tại, stable; có thể ném `UnsupportedOperationException` nếu List không hỗ trợ sửa phần tử.
- **`Stream.sorted(comparator)`:** tạo một pipeline có thứ tự sắp xếp mà không sửa nguồn; với ordered stream, sort ổn định; với unordered stream, stability không được đảm bảo.
- **`Arrays.sort(Object[], comparator)`:** sắp mảng object và bảo đảm stable đối với phần tử được comparator xem là ngang nhau.
- **`PriorityQueue<>(Comparator.reverseOrder())`:** đổi phần tử được ưu tiên bởi `poll`/`peek`; **iterator của PriorityQueue không có cam kết sắp theo priority**.
- **`TreeSet/TreeMap`:** comparator không chỉ xác định thứ tự mà còn quyết định các khóa được coi là tương đương theo compare.

Ví dụ với hàng đợi ưu tiên:

```java
PriorityQueue<Integer> queue =
        new PriorityQueue<>(Comparator.reverseOrder());

queue.add(20);
queue.add(10);
queue.add(30);

System.out.println(queue.poll()); // 30
```

Đừng dùng `forEach` trên queue để lấy danh sách đã sort; hãy dùng `poll` theo hợp đồng ưu tiên hoặc chuyển sang List rồi sort khi cần kết quả có thứ tự.

## 13. Kiểm thử comparator đúng phạm vi đảo

Một bộ kiểm thử tốt cần có:

1. Hai phần tử khác nhau ở tiêu chí chính, để chứng minh thứ tự ưu tiên.
2. Hai phần tử giống nhau ở tiêu chí chính nhưng khác tiêu chí phụ, để kiểm tra chiều của tiêu chí phụ.
3. Hai phần tử hòa cả hai tiêu chí đầu và khác tie-breaker, để kiểm tra hướng cuối cùng.
4. `null` nếu nghiệp vụ cho phép, để tránh vô tình đảo `nullsFirst`/`nullsLast`.
5. Giá trị biên của kiểu `int`/`long` để phát hiện cách viết dùng phép trừ bị tràn.
6. Trường hợp comparator trả `0` cho các object khác nhau, để kiểm tra hậu quả trong `List.sort` và `TreeSet`.

Ví dụ điều kiện test (dựa trên `Staff` trong ví dụ đầy đủ):

```java
Comparator<Staff> cmp = Comparator
        .comparing(Staff::department)
        .thenComparing(Comparator.comparingInt(Staff::score).reversed())
        .thenComparing(Staff::name);

Staff a = new Staff("Sales", "A", 90);
Staff b = new Staff("Sales", "B", 70);
Staff c = new Staff("Tech", "C", 95);

assert cmp.compare(a, b) < 0; // Cùng phòng ban: 90 đứng trước 70.
assert cmp.compare(b, c) < 0; // Sales đứng trước Tech.
```

Java `assert` có thể bị tắt trừ khi chạy `-ea`. Trong dự án thực, dùng JUnit Jupiter hoặc assertion framework tương đương.

Khi muốn kiểm tra `reversed` đúng quy tắc, hãy so sánh **dấu** của kết quả, không giả định comparator luôn trả -1 hoặc 1:

```java
int sign1 = Integer.signum(cmp.compare(a, b));
int sign2 = Integer.signum(cmp.reversed().compare(a, b));

// sign2 == -sign1, nếu cmp thỏa hợp đồng Comparator.
```

Không tự viết `return -cmp.compare(a,b)` như một thay thế tổng quát: negation của `Integer.MIN_VALUE` vẫn là `Integer.MIN_VALUE` vì tràn `int`.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `reversed()` ở cuối chuỗi khi chỉ muốn đảo score | Tất cả tiêu chí bị đảo | Đảo `comparingInt(score)` trước khi `thenComparing` |
| `reversed()` trước `thenComparing` nhưng mong đảo cả chuỗi | Chỉ phần trước được đảo | Đảo sau toàn bộ chuỗi khi đó là yêu cầu |
| Dùng `reverseOrder` cho comparator phức tạp | Không biểu đạt thứ tự multi-field | Dùng `reversed` trên comparator đúng phạm vi |
| Dùng `nullsLast(naturalOrder).reversed()` mà vẫn muốn null cuối | Null nhảy lên đầu | `nullsLast(reverseOrder())` |
| Không có tie-breaker trong `TreeSet` | Các object ngang theo comparator có thể bị coi trùng | Thêm ID duy nhất theo nghiệp vụ |
| Dùng `b-a` khi so sánh `int` | Có thể tràn số, sai dấu | `Integer.compare` hoặc `comparingInt` |
| Dùng `Collections.reverse` thay vì sort trực tiếp giảm dần | Đảo cả thứ tự của các phần tử tie | Sort bằng comparator đúng chiều |
| Dựa vào thứ tự của `PriorityQueue.iterator()` | Iterator không cam kết sort order | `poll` theo priority hoặc sort một List |
| Comparator đọc trạng thái mutable đang đổi | Kết quả sort có thể sai/hỏng hợp đồng | Ổn định các khóa trước khi sort |
| Giả định `reversed` sửa comparator hay List gốc | Không có tác dụng phụ mong đợi | Truyền comparator mới vào `sort`/`sorted` |

## 15. Bài tập và gợi ý đáp án

**Bài 1:** Viết comparator cho điểm giảm dần, tên tăng dần.

```java
Comparator<Person> cmp = Comparator.comparingInt(Person::score)
        .reversed()
        .thenComparing(Person::name);
```

`Person` là lớp giả định có hai getter tương ứng. Do `reversed` được gọi khi chuỗi mới có score, tên được thêm sau và vẫn tăng dần.

**Bài 2:** Viết comparator cho phòng ban tăng dần, điểm giảm dần, tên giảm dần.

```java
Comparator<Staff> cmp = Comparator
        .comparing(Staff::department)
        .thenComparing(Comparator.comparingInt(Staff::score).reversed())
        .thenComparing(Comparator.comparing(Staff::name).reversed());
```

**Bài 3:** Với `["b", null, "a"]`, sort các chữ giảm dần, null cuối. Đáp án: `Comparator.nullsLast(Comparator.reverseOrder())`, kết quả `[b, a, null]`.

**Bài 4:** `A.thenComparing(B).reversed()` có tương đương `A.reversed().thenComparing(B)` không? **Không.** Biểu thức thứ nhất đảo A và B; biểu thức thứ hai chỉ đảo A.

**Bài 5:** Vì sao đảo List bằng `Collections.reverse` không hoàn toàn giống sort bằng comparator đảo? Vì stable sort giữ thứ tự tương đối khi compare bằng 0, còn reverse vị trí sẽ lật cả những phần tử tie.

**Bài 6:** Khi hai object khác nhau có cùng điểm, một `TreeSet` chỉ so sánh `score` có giữ cả hai không? Có thể **không**; comparator cho compare bằng 0 làm chúng tương đương với `TreeSet`. Thêm khóa duy nhất nếu cần giữ cả hai.

**Bài 7:** Vì sao tránh `(a,b)->b-a`? Vì tràn số có thể làm mất tính đúng đắn của comparator; dùng `Integer.compare(b,a)` hoặc comparator primitive đảo.

## 16. Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 26 — Comparator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): `reversed`, `reverseOrder`, `thenComparing`, `comparingInt`, `nullsFirst`/`nullsLast` và hợp đồng `compare`.
- [Oracle Java SE 26 — List](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): `sort` là stable sort.
- [Oracle Java SE 26 — Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): `sorted`, ordered/unordered và tính ổn định.
- [Oracle Java SE 26 — PriorityQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PriorityQueue.html): ảnh hưởng của comparator lên priority.
- [Oracle Java SE 8 — Comparator](https://docs.oracle.com/javase/8/docs/api/java/util/Comparator.html): kiểm chứng các API đã có trong Java 8.

**Kết luận:** `reversed()` luôn áp dụng lên **Comparator nhận lời gọi đó**. Nếu comparator đã ghép A+B+C, đảo nó là đảo toàn bộ A+B+C. Nếu chỉ muốn đảo B, hãy viết `A.thenComparing(B.reversed()).thenComparing(C)`. Chú ý đặc biệt `nullsLast`, tie-breaker và tính nhất quán của so sánh số.
