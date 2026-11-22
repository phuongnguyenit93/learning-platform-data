# `Comparator.reversed()` và vị trí áp dụng trong chuỗi so sánh

## 1. Quy tắc cốt lõi

`Comparator<T>` mô tả thứ tự so sánh của các đối tượng kiểu `T`. Trong Java, phương thức **`reversed()` trả về một comparator mới đảo chiều thứ tự của chính comparator mà nó được gọi trên đó**. Điều này đặc biệt quan trọng khi kết hợp nhiều tiêu chí bằng `thenComparing(...)` hoặc `thenComparingInt(...)`.

Ví dụ, sắp xếp nhân viên theo:

1. `department` (phòng ban), tăng dần.
2. Nếu cùng phòng ban, `age` (tuổi), tăng dần.

Ta có thể viết:

~~~java
Comparator<Employee> byDepartment =
        Comparator.comparing(Employee::department);
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> base = byDepartment.thenComparing(byAge);
~~~

Đây là **đoạn minh họa**, giả định lớp hoặc record `Employee` có hai accessor `department()` và `age()`. `thenComparing` chỉ dùng tiêu chí tiếp theo **khi comparator trước đó trả về `0`**. Đây là kiểu so sánh từ trái sang phải (*lexicographic ordering*).

Điểm dễ nhầm là `reversed()` **đảo toàn bộ comparator đã được xây dựng đến vị trí lời gọi**, chứ không chỉ mặc định đảo tiêu chí đứng ngay cạnh nó. Hãy nghĩ theo cách đặt dấu ngoặc:

~~~text
(c1.thenComparing(c2)).reversed()
    -> đảo thứ tự của cả chuỗi c1 rồi c2

c1.reversed().thenComparing(c2)
    -> đảo c1; nếu hòa ở c1, c2 vẫn giữ chiều cũ

c1.thenComparing(c2.reversed())
    -> giữ c1; nếu hòa ở c1, đảo riêng c2
~~~

**Thứ tự lời gọi phương thức quyết định phạm vi đảo chiều.** `reversed()` không biến đổi dữ liệu gốc, không tự sắp xếp danh sách, và không thay đổi cách `equals()` của các đối tượng hoạt động.

## 2. Hiểu dấu của `compare(a, b)`

Theo hợp đồng `Comparator.compare(a, b)`:

- Trả về **số âm**: `a` đứng trước `b`.
- Trả về **`0`**: hai đối tượng tương đương theo comparator đang xét; `thenComparing` mới cần kiểm tra tiêu chí tiếp theo.
- Trả về **số dương**: `a` đứng sau `b`.

Nếu `c` là comparator tăng dần và `r = c.reversed()`, về mặt thứ tự `r.compare(a, b)` đảo dấu so sánh so với `c.compare(a, b)`. Có thể hình dung thông qua việc hoán đổi hai đối số khi so sánh. **Không nên tự đảo bằng phép trừ hoặc bằng cách đổi dấu nguyên vẹn giá trị `compare`**: giá trị `int` nhỏ nhất (`Integer.MIN_VALUE`) có thể gây tràn khi lấy đối, còn hợp đồng chỉ dựa vào dấu của kết quả.

Với tiêu chí đầu tiên `c1`, thứ hai `c2`, comparator ghép hoạt động về mặt logic như sau:

~~~java
// Minh họa thuật toán, giả sử có Comparator<T> c1 và c2.
int result = c1.compare(a, b);
if (result != 0) {
    return result;
}
return c2.compare(a, b);
~~~

`thenComparing` không “trộn” các điểm số với nhau. Tiêu chí đầu tiên có **ưu tiên cao hơn**: chỉ khi bằng nhau theo tiêu chí trước mới đi đến tiêu chí kế tiếp.

## 3. Bốn cách đặt `reversed()`, bốn thứ tự khác nhau

Giả sử mỗi đối tượng có ba thành phần:

- `name`: nhãn để quan sát đầu ra.
- `group`: một trong hai giá trị `A` hoặc `B`.
- `score`: `10` hoặc `20`.

Ta muốn sắp xếp theo `group` trước, rồi theo `score`.

| Cách tạo comparator | Group | Score trong cùng group | Ý nghĩa |
| --- | --- | --- | --- |
| `byGroup.thenComparing(byScore)` | A → B | 10 → 20 | Cả hai tăng dần |
| `byGroup.thenComparing(byScore).reversed()` | B → A | 20 → 10 | Đảo **toàn chuỗi** đã tạo |
| `byGroup.reversed().thenComparing(byScore)` | B → A | 10 → 20 | Đảo **group** trước khi gắn score |
| `byGroup.thenComparing(byScore.reversed())` | A → B | 20 → 10 | Chỉ đảo **score** làm tiêu chí phụ |

Chú ý: `byGroup.reversed().thenComparing(byScore)` là một comparator mới được xây dựng theo thứ tự *group giảm, score tăng*. Nếu gọi thêm `.reversed()` **sau toàn bộ chuỗi này**, bạn lại đảo cả hai tiêu chí đang có, trở thành *group tăng, score giảm*.

Một cách diễn đạt toán học tiện nhớ:

~~~text
(c1 + c2).reversed()  ≈  c1.reversed() + c2.reversed()
c1.reversed() + c2    =  c1 giảm, rồi c2 theo chiều ban đầu
c1 + c2.reversed()    =  c1 theo chiều ban đầu, rồi c2 giảm
~~~

Dấu `+` ở đây chỉ cách ghép comparator bằng `thenComparing`, **không phải phép cộng Java**. Dấu `≈` diễn tả **tương đương về thứ tự so sánh**, không khẳng định hai đối tượng comparator có cùng tham chiếu hay cùng cấu trúc triển khai.

## 4. Chương trình Java 17+ chạy độc lập

Tạo tệp **`ComparatorReversedDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;

public class ComparatorReversedDemo {
    record Row(String name, String group, int score) {}

    static void show(
            String label, List<Row> rows, Comparator<Row> comparator) {
        List<String> names = rows.stream()
                .sorted(comparator)
                .map(Row::name)
                .toList();
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(
                new Row("b20", "B", 20),
                new Row("a10", "A", 10),
                new Row("b10", "B", 10),
                new Row("a20", "A", 20));

        Comparator<Row> byGroup = Comparator.comparing(Row::group);
        Comparator<Row> byScore = Comparator.comparingInt(Row::score);

        Comparator<Row> allAsc =
                byGroup.thenComparing(byScore);

        Comparator<Row> allDesc =
                byGroup.thenComparing(byScore).reversed();

        Comparator<Row> groupDescScoreAsc =
                byGroup.reversed().thenComparing(byScore);

        Comparator<Row> groupAscScoreDesc =
                byGroup.thenComparing(byScore.reversed());

        show("group ASC, score ASC", rows, allAsc);
        show("all DESC", rows, allDesc);
        show("group DESC, score ASC", rows, groupDescScoreAsc);
        show("group ASC, score DESC", rows, groupAscScoreDesc);

        List<Row> ties = List.of(
                new Row("m1", "A", 10),
                new Row("m2", "A", 10),
                new Row("x", "B", 20));

        show("reverse with equal keys", ties, allDesc);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac ComparatorReversedDemo.java
java ComparatorReversedDemo
~~~

Đầu ra xác định:

~~~text
group ASC, score ASC: [a10, a20, b10, b20]
all DESC: [b20, b10, a20, a10]
group DESC, score ASC: [b10, b20, a10, a20]
group ASC, score DESC: [a20, a10, b20, b10]
reverse with equal keys: [x, m1, m2]
~~~

**Giải thích từng dòng:**

1. `allAsc` là chuỗi tăng dần theo `group` rồi tăng dần theo `score`: các dòng nhóm `A` đứng trước nhóm `B`; trong mỗi nhóm điểm `10` đứng trước `20`.
2. `allDesc` gọi `reversed()` **sau khi `thenComparing` đã gắn cả hai tiêu chí**. Vì thế nhóm `B` đứng trước `A`, đồng thời điểm `20` đứng trước `10` trong từng nhóm.
3. `groupDescScoreAsc` gọi `reversed()` khi comparator mới chỉ có `byGroup`. Sau đó `thenComparing(byScore)` gắn tiêu chí điểm **giữ nguyên tăng dần**.
4. `groupAscScoreDesc` đảo đúng comparator `byScore` trước khi đưa vào `thenComparing`. Nhóm vẫn tăng dần, điểm bên trong nhóm giảm dần.
5. Hai dòng `m1` và `m2` có cùng `group = A` và `score = 10`, nên `allDesc.compare(m1, m2) == 0`. `Stream.sorted` giữ tính ổn định (*stable*) đối với stream có thứ tự như `List.stream()`, nên hai dòng hòa vẫn xuất hiện theo thứ tự nhập ban đầu: `m1` trước `m2`.

**Bài học quan trọng:** đảo comparator **không đồng nghĩa đảo ngược toàn bộ danh sách đã sắp xếp**. Nếu các phần tử có khóa so sánh bằng nhau, sort ổn định giữ thứ tự tương đối của chúng; còn lệnh đảo danh sách như `Collections.reverse(list)` sẽ đổi cả thứ tự các phần tử hòa đó.

## 5. Vị trí `reversed()` khi có ba tiêu chí

Giả sử cần sắp xếp theo ba khóa lần lượt: **phòng ban, lương, tên**. Từ trái sang phải, `thenComparing` chỉ được dùng khi toàn bộ tiêu chí trước đó cho kết quả hòa.

### A. Đảo mọi tiêu chí đã ghép

~~~java
// Đoạn minh họa trong ngữ cảnh có lớp Employee và các accessor.
Comparator<Employee> allDescending =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name)
                .reversed();
~~~

Thứ tự là **phòng ban giảm → lương giảm → tên giảm**. `reversed()` nằm ở cuối nên bao trùm **toàn bộ ba khóa**.

### B. Đảo tiêu chí thứ nhất, các tiêu chí sau tăng dần

~~~java
Comparator<Employee> departmentDescThenOthersAsc =
        Comparator.comparing(Employee::department,
                             Comparator.reverseOrder())
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name);
~~~

Ở đây chỉ đảo việc so sánh `department` ngay khi tạo comparator gốc, rồi gắn các tiêu chí phụ giữ nguyên. Một biểu thức có thứ tự tương đương là:

~~~java
Comparator<Employee> byDepartment =
        Comparator.comparing(Employee::department);

Comparator<Employee> departmentDescThenOthersAsc =
        byDepartment.reversed()
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name);
~~~

Đây là **hai phương án thay thế**, không đặt cả hai khai báo biến trùng tên trong cùng một scope.

### C. Chỉ đảo tiêu chí ở giữa

~~~java
Comparator<Employee> middleDescending =
        Comparator.comparing(Employee::department)
                .thenComparing(
                        Comparator.comparingInt(Employee::salary)
                                  .reversed())
                .thenComparing(Employee::name);
~~~

Thứ tự: **phòng ban tăng → lương giảm → tên tăng**.

Nếu Java gặp vấn đề suy luận kiểu với một lambda hoặc method reference phức tạp ở comparator bên trong, tách biến với kiểu tường minh:

~~~java
Comparator<Employee> salaryDesc =
        Comparator.comparingInt(Employee::salary).reversed();

Comparator<Employee> middleDescending =
        Comparator.comparing(Employee::department)
                .thenComparing(salaryDesc)
                .thenComparing(Employee::name);
~~~

Mỗi đoạn đều là **minh họa**, giả định `Employee` có `department()` và `name()` trả về `String`, `salary()` trả về `int`, đồng thời đã import `java.util.Comparator`. Chỉ chương trình trong mục 4 là tệp Java hoàn chỉnh để chạy độc lập.

### D. Đảo phần tiền tố rồi thêm tiêu chí mới

~~~java
Comparator<Employee> prefixDescNameAsc =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary)
                .reversed()
                .thenComparing(Employee::name);
~~~

Thứ tự: **phòng ban giảm → lương giảm → tên tăng**. `reversed()` đảo *hai tiêu chí đã ghép trước đó*, còn `thenComparing(Employee::name)` được thêm **sau bước đảo** nên vẫn tăng dần.

Đây là khác biệt quan trọng so với việc chuyển `reversed()` xuống cuối cùng: khi chuyển xuống cuối, tên cũng sẽ giảm dần.

## 6. Hai cách viết “đảo một tiêu chí”

Khi muốn đảo một khóa cụ thể, có hai lựa chọn thường rõ ràng hơn việc đặt `reversed()` vào giữa chuỗi dài:

**Cách 1: truyền comparator dành riêng cho khóa vào `comparing` / `thenComparing`.**

~~~java
Comparator<Employee> byDepartmentDescThenNameAsc =
        Comparator.comparing(
                Employee::department, Comparator.reverseOrder())
                .thenComparing(Employee::name);
~~~

`Comparator.reverseOrder()` tạo comparator theo thứ tự ngược lại **thứ tự tự nhiên** của kiểu giá trị khóa. Với `String`, thứ tự tự nhiên là từ điển theo giá trị Unicode; với `Integer`, đó là thứ tự số tăng dần. Vì `department` trả về `String` nên cách này đảo riêng khóa phòng ban.

**Cách 2: tạo comparator con rồi gọi `reversed()` đúng vào comparator con.**

~~~java
Comparator<Employee> bySalaryDesc =
        Comparator.comparingInt(Employee::salary).reversed();

Comparator<Employee> byDepartmentAscSalaryDesc =
        Comparator.comparing(Employee::department)
                .thenComparing(bySalaryDesc);
~~~

Cách này đặc biệt dễ đọc khi khóa phụ là số nguyên thủy: `comparingInt` dùng bộ trích xuất `int`, rồi `reversed()` đảo comparator kết quả.

**Lưu ý:** `Comparator.reverseOrder()` là phương thức `static` tạo comparator ngược với thứ tự tự nhiên của **chính kiểu khóa**; `someComparator.reversed()` là phương thức của comparator hiện có, đảo thứ tự do **comparator đó định nghĩa**, kể cả khi nó gồm nhiều khóa hoặc quy tắc tùy biến.

## 7. `reversed()` không làm mất ưu tiên của `thenComparing`

Xét:

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary);
~~~

Nếu hai nhân viên khác phòng ban, kết quả so sánh đã được quyết định tại `department`; lương của họ không được dùng làm tiêu chí để “vượt qua” thứ tự phòng ban. Gọi `cmp.reversed()` chỉ đảo thứ tự phân nhóm và đảo cách phân thứ tự lương **trong cùng phòng ban**.

Tương tự, nếu viết `cmp.reversed().thenComparing(Employee::name)`, tiêu chí `name` chỉ hoạt động khi **cả phòng ban và lương** không phân biệt được hai nhân viên. Nó không thay thế, cũng không chen lên trước các tiêu chí đó.

Vì vậy, khi kết quả sort khác mong muốn, hãy đọc chuỗi comparator như một **danh sách tiêu chí ưu tiên**: “so sánh khóa 1; nếu hòa thì khóa 2; nếu vẫn hòa thì khóa 3”. Sau đó xác định chính xác `reversed()` đã bao phủ những tiêu chí nào vào thời điểm gọi.

## 8. Các trường hợp cần lưu ý

### Khóa `null` và vị trí `nullsFirst`/`nullsLast`

Khi có khóa có thể là `null`, `Comparator.naturalOrder()` và `Comparator.reverseOrder()` thông thường không tự cho phép `null`. Có thể dùng `Comparator.nullsFirst(...)` hoặc `Comparator.nullsLast(...)` để định nghĩa vị trí của `null`.

Ví dụ:

~~~java
// Đoạn minh họa với giá trị kiểu String.
Comparator<String> nullLastAsc =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> nullFirstDesc = nullLastAsc.reversed();

Comparator<String> nullLastDesc =
        Comparator.nullsLast(Comparator.reverseOrder());
~~~

- `nullLastAsc`: các chuỗi không null tăng dần; `null` đứng cuối.
- `nullFirstDesc`: đảo **toàn bộ** `nullLastAsc`; chuỗi không null giảm dần **và `null` chuyển lên đầu**.
- `nullLastDesc`: các chuỗi không null giảm dần nhưng **`null` vẫn đứng cuối**.

Điều này minh họa thêm rằng `reversed()` đảo thứ tự của **cả comparator hiện tại**, bao gồm quy tắc dành cho `null` nếu quy tắc đó đã được bọc vào comparator trước lúc đảo.

### `compare(...) == 0` và các tập hợp có thứ tự

Hai đối tượng khác nhau theo `equals()` vẫn có thể có `comparator.compare(a, b) == 0` nếu mọi khóa được chọn đều bằng nhau. `TreeSet` và `TreeMap` dựa trên comparator để xác định hai phần tử hoặc khóa tương đương trong cấu trúc; vì vậy chúng có thể coi hai đối tượng khác nhau về mặt `equals()` là cùng khóa nếu comparator trả về `0`.

Nếu muốn giữ các đối tượng phân biệt theo một khóa định danh, thêm `thenComparing(Employee::id)` hoặc tiêu chí kết thúc phù hợp với ngữ nghĩa dữ liệu. Chú ý: việc thêm tiêu chí kết thúc **trước hay sau `reversed()`** tiếp tục quyết định chiều của tiêu chí đó.

### Comparator có thứ tự không hợp lệ

Một comparator phải tuân thủ hợp đồng về dấu đối xứng, tính bắc cầu và nhất quán. Chẳng hạn viết `return a.score() - b.score();` có nguy cơ tràn số nguyên, khiến dấu không phản ánh thứ tự số thực. Nên dùng `Comparator.comparingInt(Employee::score)` hoặc `Integer.compare(a.score(), b.score())`.

`reversed()` không thể sửa một comparator gốc đã vi phạm hợp đồng. Một comparator sai có thể khiến các thuật toán sắp xếp hoặc cấu trúc có thứ tự hoạt động không như mong muốn.

### Chữ hoa, chữ thường và Locale

`Comparator.comparing(Employee::name)` dùng thứ tự tự nhiên của `String`, không tự động áp dụng quy tắc ngôn ngữ cho tên người. Nếu cần thứ tự dành cho một ngôn ngữ, hãy chọn comparator khóa phù hợp (chẳng hạn `Collator` được cấu hình đúng) rồi mới đảo chiều khi cần. Việc đảo một comparator ngôn ngữ áp dụng cho **chính thứ tự mà comparator đó tạo ra**.

## 9. So sánh nhanh các biểu thức thường gặp

| Biểu thức | Tiêu chí thứ nhất | Tiêu chí thứ hai |
| --- | --- | --- |
| `c1.thenComparing(c2)` | Chiều c1 | Chiều c2 |
| `c1.thenComparing(c2).reversed()` | Ngược c1 | Ngược c2 |
| `c1.reversed().thenComparing(c2)` | Ngược c1 | Chiều c2 |
| `c1.thenComparing(c2.reversed())` | Chiều c1 | Ngược c2 |
| `c1.reversed().thenComparing(c2).reversed()` | Chiều c1 | Ngược c2 |

Trong bảng, `c1` và `c2` là các comparator hợp lệ cho **cùng kiểu phần tử**. “Chiều” được hiểu theo quy tắc do từng comparator gốc xác định, không nhất thiết là thứ tự tự nhiên. Ví dụ dòng cuối: bước đảo thứ nhất tác động vào `c1`, sau đó ghép `c2`; bước đảo cuối cùng đảo toàn bộ chuỗi đang có, nên `c1` quay về chiều ban đầu còn `c2` trở thành ngược chiều.

Khi chuỗi dài, thường nên **đặt tên các comparator con** thay vì liên tiếp gọi nhiều `reversed()`. Tên như `byGroupDesc`, `byScoreAsc` giúp kiểm tra trực tiếp yêu cầu nghiệp vụ.

## 10. Bài tập tự kiểm tra

**Câu 1.** Kết quả của chuỗi sau theo khóa phòng ban và tuổi là gì?

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .reversed()
                .thenComparingInt(Employee::age);
~~~

**Đáp án:** Phòng ban **giảm dần**, sau đó tuổi **tăng dần** trong cùng phòng ban.

**Câu 2.** Muốn cả phòng ban và tuổi cùng giảm dần thì viết thế nào?

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::age)
                .reversed();
~~~

**Đáp án:** Đặt `reversed()` sau khi đã ghép cả hai tiêu chí như trên, hoặc đảo từng comparator con rồi ghép lại.

**Câu 3.** Muốn phòng ban tăng dần, tuổi giảm dần, tên tăng dần thì làm sao?

~~~java
Comparator<Employee> ageDesc =
        Comparator.comparingInt(Employee::age).reversed();

Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparing(ageDesc)
                .thenComparing(Employee::name);
~~~

**Đáp án:** Đảo comparator `ageDesc` trước khi gắn làm tiêu chí thứ hai; `department` và `name` vẫn theo chiều tự nhiên.

**Câu 4.** `cmp.reversed()` có giống `Collections.reverse(sortedList)` không?

**Đáp án:** Không hoàn toàn. Đảo comparator rồi sắp xếp lại tạo thứ tự ngược theo các khóa so sánh, nhưng các đối tượng mà comparator coi là bằng nhau có thể giữ nguyên thứ tự tương đối khi dùng thuật toán sắp xếp ổn định. `Collections.reverse` đảo vị trí tất cả phần tử, kể cả các phần tử hòa.

**Câu 5.** Nếu `Comparator.nullsLast(Comparator.naturalOrder()).reversed()` được dùng, vị trí `null` là ở đâu?

**Đáp án:** `null` chuyển lên **đầu**, vì `reversed()` đảo cả chính sách null đã được gắn trong comparator.

**Ghi nhớ:** `reversed()` tác động đến **toàn bộ comparator đã hình thành tại điểm gọi**. Muốn đảo mọi khóa đã ghép, gọi ở cuối. Muốn đảo riêng một khóa, đảo comparator con của khóa ấy trước khi ghép hoặc cung cấp comparator đảo chiều trong `comparing`/`thenComparing`. Luôn kiểm tra thứ tự ưu tiên khi có nhiều tiêu chí.

## Tham khảo

- [Java SE 17 — `Comparator` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — `Stream.sorted` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator))
