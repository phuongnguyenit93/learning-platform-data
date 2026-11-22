# Xử lý danh sách sinh viên với nhiều tiêu chí sắp xếp

Trong một hệ thống quản lý đào tạo, danh sách sinh viên hiếm khi chỉ được sắp xếp theo một thuộc tính. Ví dụ, khi xét học bổng, nhà trường muốn ưu tiên **điểm trung bình (GPA) cao nhất**, nếu bằng điểm thì ưu tiên **số tín chỉ tích lũy nhiều hơn**, tiếp theo là **tên sinh viên**, và cuối cùng là **mã sinh viên** để tránh kết quả phụ thuộc vào thứ tự nhập dữ liệu.

Bài thực hành **“Xử lý danh sách sinh viên với nhiều tiêu chí sắp xếp”** thuộc chương **Bài tập nền tảng và trung cấp** của module **JAVA_STREAM_API**. Ta sử dụng pipeline khai báo `filter`, `map`, `sorted`, `limit` và `collect`, kết hợp `Comparator` để giải bài toán thật. Đồng thời, bài tập giúp nhận diện giới hạn của Stream về **thứ tự gặp (encounter order)**, tính lazy, trạng thái, tính bất biến của kết quả, độ phức tạp, xử lý song song và khả năng bảo trì.

Sau bài này, bạn có thể:

- Xây `Comparator<Student>` gồm nhiều tiêu chí tăng/giảm độc lập.
- Đọc và sửa lỗi thường gặp khi gọi `reversed()` sai vị trí.
- Lọc và sắp xếp dữ liệu sinh viên mà không sửa danh sách nguồn.
- Lấy top N, sắp xếp trong từng khoa và kiểm tra kết quả bằng dữ liệu kỳ vọng.
- Phân biệt thứ tự ổn định, quy tắc phá hòa và chính sách xếp hạng đồng hạng.
- Xử lý đầu vào rỗng, `null`, GPA không hợp lệ và chi phí `sorted` trên dữ liệu lớn.

Các ví dụ chính chạy với **Java 17 trở lên** để dùng `record`, `List.of` và `Stream.toList()`. Bản thân `Stream.sorted` và các hàm xây `Comparator` đã có từ Java 8.

## 1. Đọc đề bài và xác định chính sách sắp xếp

Một bản ghi sinh viên có những trường:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `code` | `String` | Mã sinh viên, dùng làm khóa định danh |
| `name` | `String` | Tên hiển thị |
| `major` | `String` | Khoa/ngành học |
| `gpa` | `double` | Điểm trung bình trên thang 4 |
| `credits` | `int` | Số tín chỉ tích lũy |

**Chính sách ưu tiên** cho danh sách xét học bổng:

1. `gpa` **giảm dần**: điểm cao đứng trước.
2. Nếu `gpa` bằng nhau, `credits` **giảm dần**: nhiều tín chỉ đứng trước.
3. Nếu hai giá trị trên bằng nhau, `name` **tăng dần**, không phân biệt chữ hoa/thường.
4. Nếu vẫn bằng nhau, `code` **tăng dần** để tạo kết quả xác định.

Ta viết gọn:

~~~text
GPA ↓  →  Tín chỉ ↓  →  Tên ↑  →  Mã ↑
~~~

Ký hiệu mũi tên chỉ chiều sắp xếp của từng tiêu chí, **không** có nghĩa mọi tiêu chí đều phải đảo cùng lúc.

### Dữ liệu mẫu

| Mã | Tên | Khoa/ngành | GPA | Tín chỉ |
|---|---|---|---:|---:|
| S01 | An | CNTT | 3.80 | 60 |
| S02 | Bình | Kinh tế | 3.90 | 58 |
| S03 | Chi | CNTT | 3.80 | 65 |
| S04 | Dũng | Ngôn ngữ | 3.90 | 58 |
| S05 | Hà | CNTT | 3.50 | 90 |
| S06 | Bình | CNTT | 3.90 | 58 |
| S07 | An | Kinh tế | 3.80 | 65 |
| S08 | Bình | CNTT | 3.90 | 58 |
| S09 | Lan | CNTT | 4.00 | 40 |
| S10 | Giang | CNTT | 3.20 | 95 |

Dữ liệu cố tình có các trường hợp **đồng điểm**, **đồng tín chỉ** và **trùng tên**. Nếu kết quả chỉ đúng với danh sách có điểm khác nhau hoàn toàn, comparator nhiều tiêu chí vẫn chưa được kiểm tra đủ.

## 2. Vì sao chọn Stream.sorted?

`Stream.sorted(...)` là **intermediate operation** tạo một Stream có thứ tự sắp xếp. Có hai overload quen thuộc:

~~~java
Stream<T> sorted()

Stream<T> sorted(Comparator<? super T> comparator)
~~~

`sorted()` không tham số dựa vào **thứ tự tự nhiên** của phần tử, tức phần tử phải so sánh được theo `Comparable`. Record `Student` của chúng ta **không tự triển khai `Comparable`**, nên cần dùng `sorted(comparator)`.

Ví dụ nhỏ:

~~~java
import java.util.List;

List<Integer> scores = List.of(9, 5, 7, 5);

List<Integer> ascending = scores.stream()
    .sorted()
    .toList();

System.out.println(ascending); // [5, 5, 7, 9]
System.out.println(scores);    // [9, 5, 7, 5]
~~~

`sorted` **không loại phần tử trùng**: cả hai số 5 vẫn còn. `Stream.toList()` (Java 16+) trả danh sách không thể sửa bằng các thao tác như `add` hay `sort`. Danh sách `scores` ban đầu cũng không bị thay đổi.

So sánh hai cách:

| Cách xử lý | Thay đổi nguồn? | Đầu ra |
|---|---|---|
| `students.stream().sorted(c).toList()` | Không sửa collection nguồn | Danh sách mới theo comparator |
| `students.sort(c)` | **Có**, sắp xếp trực tiếp List | Không trả List, thay đổi thứ tự phần tử trong nguồn |
| `students.stream().sorted(c).collect(toList())` | Không sửa collection nguồn | Danh sách do collector tạo, không cam kết cụ thể khả năng sửa |

Dùng `Stream.sorted` khi muốn tạo góc nhìn kết quả sắp xếp mà vẫn giữ dữ liệu đầu vào, hoặc khi sắp xếp là một bước trong pipeline nhiều thao tác.

## 3. Comparator: giá trị âm, 0 và dương

`Comparator<T>` so sánh hai giá trị `a` và `b`, trả:

- Số **âm** khi `a` được xếp trước `b`.
- **0** khi chúng được xem là cùng vị trí theo comparator.
- Số **dương** khi `a` được xếp sau `b`.

Không nên kiểm tra kết quả `compare(a, b) == -1`: hợp đồng chỉ yêu cầu **dấu** của số nguyên trả về, không yêu cầu đúng `-1` hoặc `1`.

~~~java
import java.util.Comparator;

Comparator<Integer> ascending = Integer::compare;

System.out.println(ascending.compare(2, 8) < 0); // true
System.out.println(ascending.compare(8, 2) > 0); // true
System.out.println(ascending.compare(5, 5) == 0); // true
~~~

Comparator phải tuân thủ quan hệ so sánh hợp lệ: phản đối xứng về dấu, bắc cầu và nhất quán trong lúc sắp xếp. Comparator phụ thuộc đồng hồ, số ngẫu nhiên hay biến ngoài thay đổi có thể tạo kết quả khó đoán, thậm chí gây lỗi do vi phạm hợp đồng so sánh.

### 3.1. Đừng viết comparator bằng phép trừ có nguy cơ tràn

~~~java
// Không nên khi số nguyên có thể lớn:
// Comparator<Student> wrong = (a, b) -> b.credits() - a.credits();
~~~

Với số nguyên tổng quát, phép trừ có thể tràn khiến thứ tự sai. Đối với số thực, phép trừ cũng có vấn đề với `NaN`, vô cực và các giá trị gần nhau.

Hãy sử dụng các hàm so sánh đã có:

~~~java
Comparator<Student> byCreditsAscending =
    Comparator.comparingInt(Student::credits);

Comparator<Student> byGpaAscending =
    Comparator.comparingDouble(Student::gpa);
~~~

`comparingInt` và `comparingDouble` diễn đạt ý định rõ và tránh boxing chỉ để so sánh khóa nguyên thủy.

## 4. Xây từng tiêu chí tăng dần và giảm dần

Các phương thức quan trọng:

~~~java
Comparator.comparing(...)
Comparator.comparingInt(...)
Comparator.comparingDouble(...)
Comparator.reversed()
Comparator.thenComparing(...)
~~~

Giả sử kiểu `Student` đã được khai báo như mục 7.

### 4.1. GPA giảm dần

~~~java
Comparator<Student> byGpaDesc =
    Comparator.comparingDouble(Student::gpa)
        .reversed();
~~~

Nếu `a.gpa() = 3.9` và `b.gpa() = 3.8`, comparator xem `a` đứng trước `b`.

### 4.2. Số tín chỉ giảm dần

~~~java
Comparator<Student> byCreditsDesc =
    Comparator.comparingInt(Student::credits)
        .reversed();
~~~

Phép so sánh này **chỉ** xét `credits`. Nó có thể dùng làm tiêu chí phụ sau GPA.

### 4.3. Tên tăng dần, không phân biệt hoa/thường

~~~java
Comparator<Student> byNameAsc =
    Comparator.comparing(
        Student::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

`String.CASE_INSENSITIVE_ORDER` không phân biệt hoa/thường theo quy tắc so sánh của Java, nhưng **không phải bộ sắp xếp ngôn ngữ tiếng Việt hoàn chỉnh**. Nếu giao diện phải sắp xếp tên theo quy tắc ngôn ngữ hoặc locale cụ thể, cần chọn cơ chế collation phù hợp và kiểm thử bằng dữ liệu thực tế. Bài tập này chủ động dùng quy tắc đơn giản, xác định được mà không phụ thuộc locale mặc định của máy.

### 4.4. Mã tăng dần

~~~java
Comparator<Student> byCodeAsc =
    Comparator.comparing(Student::code);
~~~

`String.compareTo` sắp theo thứ tự tự nhiên của chuỗi. Ví dụ dùng mã có độ dài thống nhất (`S01`, `S02`, …), nên thứ tự chữ phù hợp với mong đợi của dữ liệu mẫu. Với mã độ dài khác nhau như `S2` và `S10`, thứ tự từ điển không nhất thiết trùng thứ tự số; cần quy tắc tách số nếu nghiệp vụ yêu cầu.

## 5. Ghép nhiều tiêu chí với thenComparing

`thenComparing` chỉ so sánh tiêu chí tiếp theo **khi comparator trước trả 0**.

~~~java
Comparator<Student> priorityOrder =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits)
                .reversed()
        )
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);
~~~

Có thể đọc câu lệnh từ trên xuống:

~~~text
So GPA, cao hơn trước.
    Nếu bằng → so tín chỉ, nhiều hơn trước.
        Nếu bằng → so tên, tên nhỏ hơn trước.
            Nếu bằng → so mã, mã nhỏ hơn trước.
~~~

Đây là một **comparator tổng hợp**. Không cần tự viết nhiều `if` và `return` để so từng trường.

### 5.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["So sánh hai sinh viên"] --> B{"GPA khác nhau?"}
    B -->|Có| C["GPA cao đứng trước"]
    B -->|Không| D{"Tín chỉ khác nhau?"}
    D -->|Có| E["Tín chỉ nhiều đứng trước"]
    D -->|Không| F{"Tên khác nhau?"}
    F -->|Có| G["Tên tăng dần"]
    F -->|Không| H["Mã tăng dần"]
~~~

Sơ đồ áp dụng đúng chính sách đã xác định; nếu tổ chức thay tiêu chí ưu tiên, phải đổi thứ tự các bước `thenComparing` tương ứng.

## 6. Lỗi kinh điển: reversed() đặt sai vị trí

Hai đoạn code sau **không tương đương**.

**Đúng: đảo riêng tiêu chí GPA và tín chỉ.**

~~~java
Comparator<Student> correct =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits)
                .reversed()
        )
        .thenComparing(Student::name)
        .thenComparing(Student::code);
~~~

**Sai với đề bài: đảo toàn bộ comparator đã ghép.**

~~~java
Comparator<Student> wrong =
    Comparator.comparingDouble(Student::gpa)
        .thenComparingInt(Student::credits)
        .thenComparing(Student::name)
        .thenComparing(Student::code)
        .reversed();
~~~

Trong đoạn `wrong`, phương thức `reversed()` áp dụng cho **toàn bộ chuỗi so sánh**. Kết quả: GPA giảm dần **nhưng tín chỉ, tên và mã cũng đảo chiều**, trái yêu cầu “tên/mã tăng dần”.

Một lỗi tinh vi khác:

~~~java
Comparator<Student> alsoWrong =
    Comparator.comparingDouble(Student::gpa)
        .reversed()
        .thenComparingInt(Student::credits)
        .reversed();
~~~

`reversed()` cuối cùng lại đảo **toàn bộ comparator tích lũy**, khiến GPA chuyển thành tăng dần và tín chỉ thành giảm dần.

**Quy tắc:** khi tiêu chí phụ có chiều ngược tiêu chí chính, hãy tạo comparator phụ riêng rồi truyền vào `thenComparing(...)`. Cách này giúp reviewer dễ thấy và ít sửa nhầm hơn.

## 7. Chương trình hoàn chỉnh: sắp xếp danh sách sinh viên

Lưu mã dưới đây vào `StudentSortingExercise.java` và chạy bằng **Java 17+**. Chương trình tự chứa bộ dữ liệu, quy tắc kiểm tra đầu vào, comparator nhiều cấp và phần đối chiếu kết quả.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class StudentSortingExercise {

    record Student(
        String code,
        String name,
        String major,
        double gpa,
        int credits
    ) {
        Student {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("Mã sinh viên không hợp lệ");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên sinh viên không hợp lệ");
            }
            if (major == null || major.isBlank()) {
                throw new IllegalArgumentException("Khoa/ngành không hợp lệ");
            }
            if (!Double.isFinite(gpa) || gpa < 0.0 || gpa > 4.0) {
                throw new IllegalArgumentException("GPA phải trong [0, 4]");
            }
            if (credits < 0) {
                throw new IllegalArgumentException("Tín chỉ không được âm");
            }
        }
    }

    static final Comparator<Student> PRIORITY_ORDER =
        Comparator.comparingDouble(Student::gpa)
            .reversed()
            .thenComparing(
                Comparator.comparingInt(Student::credits)
                    .reversed()
            )
            .thenComparing(
                Student::name,
                String.CASE_INSENSITIVE_ORDER
            )
            .thenComparing(Student::code);

    static List<Student> sampleStudents() {
        return List.of(
            new Student("S01", "An",    "CNTT",      3.80, 60),
            new Student("S02", "Bình",  "Kinh tế",   3.90, 58),
            new Student("S03", "Chi",   "CNTT",      3.80, 65),
            new Student("S04", "Dũng",  "Ngôn ngữ",  3.90, 58),
            new Student("S05", "Hà",    "CNTT",      3.50, 90),
            new Student("S06", "Bình",  "CNTT",      3.90, 58),
            new Student("S07", "An",    "Kinh tế",   3.80, 65),
            new Student("S08", "Bình",  "CNTT",      3.90, 58),
            new Student("S09", "Lan",   "CNTT",      4.00, 40),
            new Student("S10", "Giang", "CNTT",      3.20, 95)
        );
    }

    public static void main(String[] args) {
        List<Student> students = sampleStudents();

        List<Student> sorted = students.stream()
            .sorted(PRIORITY_ORDER)
            .toList();

        List<String> actualCodes = sorted.stream()
            .map(Student::code)
            .toList();

        List<String> expectedCodes = List.of(
            "S09", "S02", "S06", "S08", "S04",
            "S07", "S03", "S01", "S05", "S10"
        );

        if (!actualCodes.equals(expectedCodes)) {
            throw new AssertionError(
                "Thứ tự không đúng: " + actualCodes
            );
        }

        System.out.println("Thứ tự ưu tiên: " + actualCodes);

        // Chỉ lấy sinh viên đạt GPA từ 3.8, sau đó chọn 3 người đầu.
        List<Student> topThree = students.stream()
            .filter(s -> s.gpa() >= 3.8)
            .sorted(PRIORITY_ORDER)
            .limit(3)
            .toList();

        System.out.println(
            "Top 3: " + topThree.stream()
                .map(Student::code)
                .collect(Collectors.joining(", "))
        );

        // In có Locale.ROOT để dấu thập phân ổn định giữa các máy.
        sorted.forEach(s -> System.out.printf(
            Locale.ROOT,
            "%s | %-7s | GPA %.2f | %d tín chỉ%n",
            s.code(), s.name(), s.gpa(), s.credits()
        ));

        // Danh sách nguồn vẫn giữ thứ tự đầu vào.
        System.out.println(
            "Phần tử đầu nguồn: " + students.get(0).code()
        ); // S01
    }
}
~~~

### 7.1. Kết quả quan trọng

~~~text
Thứ tự ưu tiên: [S09, S02, S06, S08, S04, S07, S03, S01, S05, S10]
Top 3: S09, S02, S06
Phần tử đầu nguồn: S01
~~~

Bảng kiểm tra chi tiết:

| Thứ tự | Mã | GPA | Tín chỉ | Vì sao ở vị trí này? |
|---:|---|---:|---:|---|
| 1 | S09 | 4.00 | 40 | GPA cao nhất |
| 2 | S02 | 3.90 | 58 | Đồng GPA/tín chỉ/tên với S06, S08; mã nhỏ nhất |
| 3 | S06 | 3.90 | 58 | Mã sau S02 |
| 4 | S08 | 3.90 | 58 | Mã sau S06 |
| 5 | S04 | 3.90 | 58 | Tên Dũng xếp sau Bình |
| 6 | S07 | 3.80 | 65 | Cùng GPA/tín chỉ với S03; tên An trước Chi |
| 7 | S03 | 3.80 | 65 | Tên Chi sau An |
| 8 | S01 | 3.80 | 60 | Tín chỉ ít hơn S07 và S03 |
| 9 | S05 | 3.50 | 90 | GPA thấp hơn dù tín chỉ nhiều |
| 10 | S10 | 3.20 | 95 | GPA thấp nhất, tín chỉ cao không đảo ưu tiên |

Dòng cuối của chương trình giúp chứng minh **nguồn không bị sắp xếp tại chỗ**: `List.of` ban đầu vẫn bắt đầu bằng `S01`, dù danh sách `sorted` đã bắt đầu bằng `S09`.

### 7.2. Vì sao phải có mã làm tiêu chí cuối?

Nếu chỉ so GPA, tín chỉ và tên, các sinh viên `S02`, `S06`, `S08` bằng nhau theo comparator. Với nguồn `List` có thứ tự, `Stream.sorted` ổn định (*stable*) và giữ thứ tự ban đầu giữa các phần tử comparator xem là ngang nhau.

Tuy nhiên, nếu đầu vào được thu từ nguồn không có encounter order hoặc thay đổi thứ tự nạp dữ liệu, thứ tự của nhóm đồng hạng có thể khác. Thêm `code` làm tie-breaker giúp **quy tắc hiển thị không phụ thuộc vào lịch sử chèn** khi mã sinh viên là duy nhất.

## 8. Bài tập 1 — sắp xếp theo một tiêu chí

Trước khi ghép nhiều điều kiện, hãy kiểm tra từng comparator riêng.

**Yêu cầu A:** sắp xếp GPA **tăng dần**, nếu bằng điểm thì mã tăng dần.

~~~java
Comparator<Student> gpaAscCodeAsc =
    Comparator.comparingDouble(Student::gpa)
        .thenComparing(Student::code);

List<String> codes = students.stream()
    .sorted(gpaAscCodeAsc)
    .map(Student::code)
    .toList();

System.out.println(codes);
// [S10, S05, S01, S03, S07, S02, S04, S06, S08, S09]
~~~

Ở nhóm GPA 3.80, ta dùng mã tăng dần, **không** xét tín chỉ, nên thứ tự S01 → S03 → S07. Kết quả này khác chương trình chính là điều hoàn toàn đúng vì **chính sách sắp xếp đã thay đổi**.

**Yêu cầu B:** sắp xếp số tín chỉ **giảm dần**; nếu bằng thì mã tăng dần.

~~~java
Comparator<Student> creditsDescCodeAsc =
    Comparator.comparingInt(Student::credits)
        .reversed()
        .thenComparing(Student::code);

List<String> orderedCodes = students.stream()
    .sorted(creditsDescCodeAsc)
    .map(Student::code)
    .toList();

System.out.println(orderedCodes);
// [S10, S05, S03, S07, S01, S02, S04, S06, S08, S09]
~~~

Kiểm tra: S10 có 95 tín chỉ, S05 có 90, S03/S07 có 65, S01 có 60, nhóm S02/S04/S06/S08 có 58, S09 có 40. Đây là ví dụ giúp nhận ra rằng **tiêu chí chính thay đổi thì phần tử đầu cũng thay đổi**.

## 9. Bài tập 2 — lọc, sắp xếp và lấy top N

Yêu cầu: chọn tối đa năm sinh viên thuộc ngành `CNTT` có GPA ít nhất 3.5, rồi sắp xếp theo chính sách xét học bổng.

~~~java
int topN = 5;

List<Student> topCntt = students.stream()
    .filter(s -> s.major().equals("CNTT"))
    .filter(s -> s.gpa() >= 3.5)
    .sorted(PRIORITY_ORDER)
    .limit(topN)
    .toList();

System.out.println(
    topCntt.stream().map(Student::code).toList()
);
// [S09, S06, S08, S03, S01]
~~~

Vì CNTT có S09, S06, S08, S03, S01, S05, S10 nhưng S10 không đạt 3.5; sau khi sắp, top 5 không chứa S05.

**Đặt `filter` trước `sorted`** thường có lợi vì giảm số phần tử cần sắp xếp. Pipeline vẫn mang đúng ý nghĩa “chọn sinh viên đủ điều kiện, rồi xếp thứ tự”.

### 9.1. Đổi thứ tự thao tác có thể đổi nghĩa bài toán

~~~java
List<Student> wrongForThisRequirement = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(5)
    .filter(s -> s.major().equals("CNTT"))
    .toList();
~~~

Đoạn này chọn **năm sinh viên đứng đầu toàn trường**, rồi mới giữ người thuộc CNTT. Nó **không bảo đảm** lấy đủ năm người CNTT ưu tiên cao nhất.

| Pipeline | Ý nghĩa |
|---|---|
| `filter(CNTT).sorted(priority).limit(5)` | Top 5 **trong CNTT** |
| `sorted(priority).limit(5).filter(CNTT)` | Sinh viên CNTT **nằm trong top 5 toàn trường** |

Hai mục tiêu đều có thể hợp lệ, nhưng không thể thay thế cho nhau. Khi code review, hãy đối chiếu thứ tự thao tác với câu chữ của yêu cầu.

### 9.2. Trường hợp N bằng 0 hoặc âm

`limit(0)` trả Stream không có phần tử; `limit(n)` với `n < 0` ném `IllegalArgumentException`. API nghiệp vụ nên xác thực tham số:

~~~java
static List<Student> topStudents(
        List<Student> source,
        Comparator<Student> order,
        int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit không được âm");
    }
    return source.stream()
        .sorted(order)
        .limit(limit)
        .toList();
}
~~~

Phương thức trên không chỉnh sửa `source`. Nó giả định `source` và `order` khác null; API production có thể thêm `Objects.requireNonNull` để báo lỗi sớm.

## 10. Bài tập 3 — sắp xếp trong từng khoa

Yêu cầu: tạo một `Map`, trong đó mỗi khoa có **danh sách sinh viên đã sắp xếp theo cùng chính sách ưu tiên**.

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, List<Student>> byMajor =
    students.stream()
        .collect(Collectors.groupingBy(
            Student::major,
            TreeMap::new,
            Collectors.collectingAndThen(
                Collectors.toList(),
                group -> group.stream()
                    .sorted(PRIORITY_ORDER)
                    .toList()
            )
        ));

System.out.println(
    byMajor.get("CNTT").stream()
        .map(Student::code)
        .toList()
);
// [S09, S06, S08, S03, S01, S05, S10]

System.out.println(
    byMajor.get("Kinh tế").stream()
        .map(Student::code)
        .toList()
);
// [S02, S07]
~~~

Có ba cơ chế khác nhau trong ví dụ:

1. `groupingBy(Student::major, ...)` phân loại sinh viên theo khoa.
2. `TreeMap::new` yêu cầu khóa khoa được duyệt theo thứ tự tự nhiên của `String`.
3. `collectingAndThen(toList(), ...)` nhận danh sách của **từng nhóm**, sau đó sắp xếp danh sách nhóm theo `PRIORITY_ORDER`.

**Lưu ý về khả năng sửa:** `group.stream().sorted(...).toList()` trả danh sách không thể sửa, nhưng **Map bên ngoài** do collector tạo vẫn có thể sửa trừ khi được bao/sao chép theo chính sách. Nếu cần kết quả Map không thể sửa, cân nhắc `Map.copyOf(byMajor)` sau khi thu thập; thao tác này không bảo đảm giữ thứ tự khóa như `TreeMap`, nên cần lựa chọn API theo đúng nhu cầu.

### 10.1. Không nhầm sắp xếp khóa Map với sắp xếp sinh viên

`TreeMap::new` chỉ sắp xếp **tên khoa**, không tự sắp xếp sinh viên **bên trong mỗi nhóm**. Nếu bỏ `collectingAndThen(...sorted...)`, mỗi nhóm được thu theo encounter order của nguồn (với `List` tuần tự), không nhất thiết theo GPA.

Ngược lại, `sorted(PRIORITY_ORDER)` trong downstream không làm thay đổi cách `Map` duyệt các khóa khoa.

### 10.2. Khi số lượng khoa rất lớn

`groupingBy` giữ nhiều bộ chứa trung gian; sắp xếp từng nhóm có thêm chi phí. Nếu chỉ cần top 3 trong mỗi khoa, xây toàn bộ danh sách rồi sắp xếp vẫn có thể tốn bộ nhớ. Với dữ liệu rất lớn, có thể cần collector tùy chỉnh dùng hàng đợi ưu tiên kích thước giới hạn, nhưng phải bảo đảm quy tắc gộp đúng khi chạy song song.

Ở mức nền tảng/trung cấp, ưu tiên một bản đúng, dễ kiểm thử trước; chỉ đổi thuật toán sau khi có bằng chứng về vấn đề hiệu năng.

## 11. Bài tập 4 — thay đổi bộ quy tắc cho từng màn hình

Không phải màn hình nào cũng có cùng định nghĩa “đứng đầu”.

**Màn hình học bổng:** GPA ↓, tín chỉ ↓, tên ↑, mã ↑.

**Danh sách hành chính:** Khoa ↑, tên ↑, mã ↑.

**Danh sách theo tiến độ học tập:** Tín chỉ ↓, GPA ↓, mã ↑.

Có thể xây các comparator riêng, đặt tên theo mục tiêu:

~~~java
Comparator<Student> administrativeOrder =
    Comparator.comparing(Student::major)
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);

Comparator<Student> progressOrder =
    Comparator.comparingInt(Student::credits)
        .reversed()
        .thenComparing(
            Comparator.comparingDouble(Student::gpa)
                .reversed()
        )
        .thenComparing(Student::code);
~~~

Việc dùng hai biến có tên rõ nghĩa thường dễ bảo trì hơn một hàm nhận hàng loạt cờ boolean như `sort(students, true, false, true)`. Nếu yêu cầu tạo tiêu chí động từ UI, có thể dùng enum hoặc cấu hình biểu diễn **trường**, **chiều**, **tie-breaker**; nhưng phải giới hạn các trường được phép sắp xếp và có kiểm thử cho từng tổ hợp.

### 11.1. Không dùng chung Comparator với quy tắc đang thay đổi

Một comparator không nên đọc biến global mutable rồi thay đổi chiều so sánh giữa lúc `sorted` đang chạy. Việc cùng cặp đối tượng trả hai kết quả khác nhau có thể vi phạm hợp đồng comparator.

Cách an toàn là **tạo comparator hoàn chỉnh trước pipeline** và giữ nó ổn định trong suốt quá trình sắp xếp.

## 12. Tính ổn định (stable sort) và quy tắc đồng hạng

Với một Stream **có encounter order**, `sorted` ổn định: những phần tử được comparator xem là ngang nhau giữ thứ tự xuất hiện tương đối.

Ví dụ:

~~~java
record Score(String code, int points) {}

List<Score> input = List.of(
    new Score("A", 90),
    new Score("B", 80),
    new Score("C", 90)
);

List<String> codes = input.stream()
    .sorted(Comparator.comparingInt(Score::points).reversed())
    .map(Score::code)
    .toList();

System.out.println(codes); // [A, C, B]
~~~

A và C đều 90 điểm, comparator trả 0 nên A vẫn trước C theo danh sách nguồn. Với Stream **không có thứ tự**, tính ổn định của `sorted` không được bảo đảm theo cách đó.

### 12.1. Stable sort không thay thế tie-breaker

Nếu nguồn là một `HashSet` hoặc dữ liệu được nạp với trình tự không cam kết, thứ tự của các phần tử đồng hạng có thể thay đổi. Nếu ứng dụng cần hiển thị ổn định giữa các lần chạy, thêm mã định danh duy nhất làm tiêu chí cuối, thay vì chỉ dựa vào tính stable của sort.

### 12.2. Số thứ tự dòng không phải thứ hạng đồng hạng

~~~java
List<Student> sorted = students.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

for (int i = 0; i < sorted.size(); i++) {
    System.out.println((i + 1) + ". " + sorted.get(i).code());
}
~~~

Đoạn trên in **vị trí** 1, 2, 3... trong kết quả, không tự động cho ra chính sách **xếp hạng đồng hạng**. Nếu nhà trường quy định “cùng GPA thì cùng hạng”, S02, S06, S08 và S04 đều có GPA 3.90; việc in số thứ tự khác nhau không có nghĩa các em có hạng học lực khác nhau.

Một bài toán xếp hạng phải quyết định rõ:

- **Ordinal position:** mọi dòng có số thứ tự riêng.
- **Competition rank:** đồng hạng cùng số, hạng sau bỏ số (1, 2, 2, 4).
- **Dense rank:** đồng hạng cùng số, hạng sau tăng đúng một (1, 2, 2, 3).

Đừng tự suy ra chính sách rank từ comparator. Khi đã xác định khóa dùng để **xét đồng hạng** (chỉ GPA hay cả tín chỉ), mới viết thuật toán gán rank tương ứng.

## 13. Đầu vào rỗng, null và GPA không hợp lệ

### 13.1. Danh sách rỗng

~~~java
List<Student> empty = List.of();

List<Student> sortedEmpty = empty.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

System.out.println(sortedEmpty.isEmpty()); // true
~~~

`sorted` không tự báo lỗi vì nguồn rỗng. Nhưng `findFirst()`/`min()`/`max()` trên danh sách rỗng trả `Optional.empty()`; không gọi `get()` mà chưa xử lý trường hợp thiếu dữ liệu.

### 13.2. Một đối tượng Student hoặc trường khóa bằng null

Record `Student` trong ví dụ chính **từ chối `null`** ở những trường dùng trong so sánh. Điều này giúp comparator đơn giản, tránh `NullPointerException` giữa quá trình sort.

Nếu nghiệp vụ cho phép tên thiếu, có thể thiết kế comparator riêng:

~~~java
Comparator<Student> nullableNameOrder =
    Comparator.comparing(
        Student::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    );
~~~

Nhưng đoạn này chỉ có ý nghĩa nếu **mô hình Student cho phép name null**; record `Student` ở mục 7 cố ý không cho phép. Không thêm `nullsLast` để che một dữ liệu đầu vào vốn phải được coi là lỗi.

### 13.3. NaN, vô cực và điểm ngoài thang

`Double.compare` có quy tắc so sánh cho `NaN`, `Infinity` và các trường hợp dấu của số 0. Nếu không kiểm tra đầu vào, `Comparator.comparingDouble(Student::gpa)` có thể đặt các giá trị đặc biệt vào thứ tự hợp lệ về mặt Java nhưng vô nghĩa với học vụ.

Bởi vậy constructor kiểm tra:

~~~java
if (!Double.isFinite(gpa) || gpa < 0.0 || gpa > 4.0) {
    throw new IllegalArgumentException("GPA phải trong [0, 4]");
}
~~~

Nếu dữ liệu điểm cần chính xác tới phần trăm hoặc theo quy tắc làm tròn đặc thù, hãy cân nhắc lưu GPA bằng **số nguyên đã nhân hệ số** hoặc `BigDecimal` với chính sách rõ ràng. Không dựa vào `==` của `double` để quyết định “điểm bằng nhau sau làm tròn” nếu nghiệp vụ yêu cầu làm tròn.

### 13.4. Chuẩn hóa tên trước khi so

`"An"` và `" An "` không bằng nhau theo `String` thông thường; khoảng trắng có thể làm lệch thứ tự. Với dữ liệu nhập từ người dùng, có thể chuẩn hóa khi parse:

~~~java
String cleaned = rawName == null ? null : rawName.trim();
~~~

Nếu cần chuẩn hóa Unicode, khoảng trắng nhiều loại hoặc ký tự tiếng Việt theo chuẩn cụ thể, hãy tạo một quy tắc chuẩn hóa có kiểm thử. Không dựa vào locale mặc định của máy, và không tự động đổi cách viết tên thật của người dùng khi chưa có yêu cầu.

## 14. Sắp xếp tên tiếng Việt: cân nhắc Collator

`String.compareTo` và `String.CASE_INSENSITIVE_ORDER` không thực hiện đầy đủ quy tắc **collation** theo ngôn ngữ. Khi sản phẩm yêu cầu danh sách sinh viên hiển thị theo thứ tự tên tiếng Việt, có thể xem xét `java.text.Collator`.

Ví dụ minh họa cho pipeline **tuần tự**:

~~~java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Locale vietnamese = new Locale("vi", "VN");
Collator collator = Collator.getInstance(vietnamese);
collator.setStrength(Collator.PRIMARY);

Comparator<Student> byVietnameseNameThenCode =
    Comparator.comparing(Student::name, collator)
        .thenComparing(Student::code);

List<Student> ordered = students.stream()
    .sorted(byVietnameseNameThenCode)
    .toList();
~~~

Ở đây cần hiểu:

- `Collator` sử dụng quy tắc so sánh ngôn ngữ từ runtime; quy tắc và kết quả có thể phụ thuộc dữ liệu locale/JDK.
- `PRIMARY` thường bỏ qua một số khác biệt như dấu hoặc chữ hoa/thường theo quy tắc collator, nên phải quyết định chính sách **đồng hạng** và thêm mã làm tie-breaker.
- `Collator` là đối tượng có cấu hình thay đổi được; không chia sẻ để nhiều thread vừa đọc vừa sửa `setStrength`. Nếu dùng trong xử lý đồng thời, hãy bảo đảm comparator có trạng thái được sử dụng an toàn hoặc tạo/clone collator phù hợp cho từng ngữ cảnh.

Ví dụ này là **biến thể theo yêu cầu locale**, không phải lý do thay thế mặc định comparator ở bài chính. Hãy kiểm thử với những tên có dấu thực tế theo chính sách của trường.

## 15. distinct(), Set và so sánh theo mã sinh viên

Sắp xếp khác loại trùng. `sorted` giữ mọi phần tử; `distinct` loại trùng theo `equals`/`hashCode` của đối tượng.

~~~java
List<Student> distinctStudents = students.stream()
    .distinct()
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

Vì record `Student` tạo `equals` dựa trên **tất cả thành phần**, hai record cùng `code` nhưng khác `gpa` có thể được xem là **khác nhau**. Đoạn trên không tự bảo đảm mỗi mã chỉ xuất hiện một lần.

Nếu yêu cầu “mỗi mã sinh viên là duy nhất”, review nên xác định một trong các chính sách:

1. **Từ chối** dữ liệu đầu vào có mã trùng.
2. **Giữ** bản ghi mới nhất theo thời gian cập nhật.
3. **Gộp** dữ liệu theo một quy tắc đã được chấp thuận.

Không dùng `TreeSet` với comparator chỉ theo GPA để “khử trùng theo mã”; nó có thể loại mất những sinh viên khác mã nhưng cùng GPA.

### 15.1. Phát hiện mã trùng bằng groupingBy

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByCode = students.stream()
    .collect(Collectors.groupingBy(
        Student::code,
        Collectors.counting()
    ));

List<String> duplicateCodes = countByCode.entrySet().stream()
    .filter(entry -> entry.getValue() > 1L)
    .map(Map.Entry::getKey)
    .sorted()
    .toList();

System.out.println(duplicateCodes); // [] với dữ liệu mẫu
~~~

Cách này **phát hiện** mã trùng, không tự quyết định bản ghi nào được giữ. Nếu API nghiệp vụ bắt buộc khóa duy nhất, có thể từ chối dữ liệu có `duplicateCodes` khác rỗng trước khi sắp xếp.

## 16. Chi phí sorted(), limit() và Stream song song

### 16.1. sorted là stateful intermediate operation

Để sắp xếp chính xác một nguồn hữu hạn, `sorted` thường phải **thu thập và tổ chức các phần tử cần so sánh** trước khi phát kết quả. Độ phức tạp sắp xếp so sánh thường được nhìn ở mức `O(n log n)`; bộ nhớ và chi phí cụ thể phụ thuộc nguồn và cách thực thi.

~~~java
List<Student> topTen = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(10)
    .toList();
~~~

Đừng hiểu `limit(10)` là chắc chắn chỉ cần nhìn 10 sinh viên. Vì `sorted` ở trước `limit`, pipeline thường phải xem **toàn bộ nguồn phù hợp** để xác định đúng top 10.

Nếu nguồn có hàng triệu sinh viên nhưng chỉ cần top 10, có thể cân nhắc thuật toán **heap/top-k** với chi phí khoảng `O(n log k)` và bộ nhớ khoảng `O(k)`. Đó là bài toán tối ưu nâng cao; nên làm đúng trước, đo sau.

### 16.2. Vì sao filter trước sorted thường có ích?

~~~java
List<Student> qualified = students.stream()
    .filter(s -> s.gpa() >= 3.8)
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

Với nguồn lớn, lọc trước có thể giảm số phần tử phải sắp xếp. Nhưng **chỉ chuyển `filter` đi chỗ khác khi nghĩa nghiệp vụ không đổi**. Ví dụ ở mục 9 cho thấy `limit` và `filter` không thể tùy tiện đổi chỗ.

### 16.3. Parallel Stream không phải mặc định nhanh hơn

~~~java
List<Student> parallelSorted = students.parallelStream()
    .sorted(PRIORITY_ORDER)
    .toList();
~~~

Đây là cách viết hợp lệ khi comparator thuần, không can thiệp nguồn và dữ liệu nguồn được sử dụng đúng hợp đồng. Tuy nhiên, `sorted` có thể cần nhiều phối hợp, phân vùng, cấp phát và gộp kết quả. Với danh sách nhỏ như dữ liệu mẫu, parallel thường không có lý do rõ ràng để có lợi.

Ngoài ra, **không ghi vào một ArrayList dùng chung** bên trong `parallelStream().forEach(list::add)` để tự tạo danh sách sắp xếp. Hãy dùng collector hoặc `toList()` của Stream.

Muốn quyết định có bật parallel trong sản phẩm hay không, hãy đo trên dữ liệu đại diện, kiểm tra tính đúng sequential/parallel, và cân nhắc tài nguyên CPU, bộ nhớ, băng thông cùng chi phí comparator. Không kết luận từ một lần chạy.

## 17. Kiểm thử comparator, không chỉ kiểm tra đầu ra một lần

Một bài thực hành sắp xếp tốt nên có **kiểm thử mức đơn vị** cho từng tiêu chí và một bộ dữ liệu chứa trường hợp hòa nhau.

### 17.1. Kiểm tra cặp có GPA khác nhau

~~~java
Student higher = new Student("A", "An", "CNTT", 3.9, 40);
Student lower = new Student("B", "Bình", "CNTT", 3.8, 100);

if (PRIORITY_ORDER.compare(higher, lower) >= 0) {
    throw new AssertionError("GPA cao phải đứng trước");
}
~~~

Mặc dù `lower` có 100 tín chỉ, GPA thấp hơn nên vẫn phải đứng sau.

### 17.2. Kiểm tra cặp cùng GPA nhưng khác tín chỉ

~~~java
Student moreCredits =
    new Student("A", "An", "CNTT", 3.8, 70);
Student fewerCredits =
    new Student("B", "Bình", "CNTT", 3.8, 60);

if (PRIORITY_ORDER.compare(moreCredits, fewerCredits) >= 0) {
    throw new AssertionError("Tín chỉ nhiều phải đứng trước");
}
~~~

### 17.3. Kiểm tra tên và mã ở nhóm hòa nhau

~~~java
Student an = new Student("S09", "An", "CNTT", 3.8, 60);
Student chi = new Student("S01", "Chi", "CNTT", 3.8, 60);

if (PRIORITY_ORDER.compare(an, chi) >= 0) {
    throw new AssertionError("Tên An phải đứng trước Chi");
}

Student binh2 =
    new Student("S02", "Bình", "CNTT", 3.9, 58);
Student binh8 =
    new Student("S08", "Bình", "CNTT", 3.9, 58);

if (PRIORITY_ORDER.compare(binh2, binh8) >= 0) {
    throw new AssertionError("Mã S02 phải đứng trước S08");
}
~~~

Các đoạn trên sử dụng record và `PRIORITY_ORDER` trong lớp `StudentSortingExercise`, không phải các chương trình độc lập. Có thể đưa chúng vào một phương thức `verifyComparator()` và gọi từ `main`; trong dự án thật nên dùng framework unit test như JUnit.

### 17.4. Kiểm tra tính chất so sánh trên dữ liệu mẫu

Với mọi cặp sinh viên `a`, `b` trong danh sách mẫu:

~~~java
for (Student a : students) {
    for (Student b : students) {
        int ab = Integer.signum(PRIORITY_ORDER.compare(a, b));
        int ba = Integer.signum(PRIORITY_ORDER.compare(b, a));

        if (ab != -ba) {
            throw new AssertionError("Sai phản đối xứng của comparator");
        }
    }
}
~~~

Đây là kiểm thử đơn giản cho **dấu** kết quả comparator. Để kiểm tra tính bắc cầu, cần xét các bộ ba `a`, `b`, `c` và xác minh quan hệ so sánh; với dữ liệu mẫu nhỏ có thể làm, nhưng việc duyệt mọi bộ ba có chi phí `O(n³)`. Bộ kiểm thử không thể thay thế thiết kế comparator đúng theo hợp đồng.

### 17.5. Kiểm tra danh sách sau sorted tăng theo comparator

~~~java
List<Student> ordered = students.stream()
    .sorted(PRIORITY_ORDER)
    .toList();

for (int i = 1; i < ordered.size(); i++) {
    if (PRIORITY_ORDER.compare(
            ordered.get(i - 1), ordered.get(i)) > 0) {
        throw new AssertionError("Kết quả không đúng thứ tự");
    }
}
~~~

Điều kiện quan trọng là cặp kề nhau **không nghịch chiều** theo comparator. Test này phát hiện kết quả chưa được sắp, nhưng phải đi kèm test chính sách GPA/tín chỉ/tên/mã; một comparator sai chiều hoàn toàn vẫn có thể tạo một danh sách “đã sắp” theo comparator sai.

## 18. Bài tập mở rộng có lời giải gợi ý

### Bài A — sinh viên đạt học bổng

**Đề:** chỉ lấy sinh viên GPA từ 3.75 trở lên, ít nhất 55 tín chỉ, sắp theo chính sách ưu tiên và lấy tối đa bốn người.

~~~java
List<String> scholarshipCodes = students.stream()
    .filter(s -> s.gpa() >= 3.75)
    .filter(s -> s.credits() >= 55)
    .sorted(PRIORITY_ORDER)
    .limit(4)
    .map(Student::code)
    .toList();

System.out.println(scholarshipCodes);
// [S02, S06, S08, S04]
~~~

S09 có GPA 4.00 nhưng **chỉ 40 tín chỉ**, nên bị loại theo điều kiện học bổng. Các sinh viên 3.9 với 58 tín chỉ được xét trước nhóm 3.8. Đây là ví dụ nhắc rằng **điều kiện lọc không phải tiêu chí sắp xếp**.

### Bài B — tìm sinh viên ưu tiên cao nhất của khoa

**Đề:** tìm một sinh viên đứng đầu khoa CNTT theo `PRIORITY_ORDER`. Không được gọi `get()` trực tiếp khi không tìm thấy.

~~~java
import java.util.Optional;

Optional<Student> bestCntt = students.stream()
    .filter(s -> s.major().equals("CNTT"))
    .min(PRIORITY_ORDER);

System.out.println(
    bestCntt.map(Student::code).orElse("Không có")
); // S09
~~~

Vì `PRIORITY_ORDER` đặt sinh viên **ưu tiên cao hơn** ở phía **nhỏ hơn** theo dấu comparator, `min(PRIORITY_ORDER)` trả người đứng đầu. Đây là điều dễ bị nhầm khi comparator đã đảo chiều.

### Bài C — thống kê số sinh viên theo khoa

**Đề:** đếm số sinh viên theo khoa, rồi sắp xếp các dòng thống kê theo **số lượng giảm dần**, nếu bằng nhau thì **tên khoa tăng dần**.

~~~java
Map<String, Long> counts = students.stream()
    .collect(Collectors.groupingBy(
        Student::major,
        Collectors.counting()
    ));

List<Map.Entry<String, Long>> sortedCounts =
    counts.entrySet().stream()
        .sorted(
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey())
        )
        .toList();

sortedCounts.forEach(entry ->
    System.out.println(entry.getKey() + ": " + entry.getValue())
);
~~~

Kết quả dữ liệu mẫu:

~~~text
CNTT: 7
Kinh tế: 2
Ngôn ngữ: 1
~~~

Ví dụ này chuyển từ `Stream<Student>` sang `Stream<Map.Entry<String, Long>>`. Comparator vẫn ghép nhiều tiêu chí như bài chính, nhưng **trường so sánh đã thay đổi**: số lượng và tên khoa.

### Bài D — tìm người nhiều tín chỉ nhất

**Đề:** không cần sắp xếp cả danh sách; chỉ tìm sinh viên có số tín chỉ cao nhất.

~~~java
Optional<Student> mostCredits = students.stream()
    .max(Comparator.comparingInt(Student::credits)
        .thenComparing(Student::code));

System.out.println(
    mostCredits.map(Student::code).orElse("Không có")
); // S10
~~~

`max` tìm giá trị lớn nhất theo comparator đã cung cấp. Khi chỉ cần một phần tử cực trị, nó thường phù hợp hơn việc `sorted(...).findFirst()` để sắp xếp cả nguồn.

## 19. Review code: tìm lỗi trước khi giao bài

Đoạn code sau **cố ý chứa sai sót**:

~~~java
// Đoạn code để phân tích, không phải lời giải đúng.
List<Student> result = students.parallelStream()
    .sorted(
        Comparator.comparingDouble(Student::gpa)
            .thenComparingInt(Student::credits)
            .thenComparing(Student::name)
            .reversed()
    )
    .limit(3)
    .toList();
~~~

Hãy tìm các vấn đề:

1. `reversed()` áp dụng lên **toàn comparator**, khiến các tiêu chí phụ cũng giảm dần.
2. Không có tiêu chí mã sinh viên để phá hòa sau tên, nên thứ tự các sinh viên trùng các tiêu chí có thể phụ thuộc encounter order.
3. Không có kiểm tra GPA hợp lệ nếu mô hình dữ liệu cho phép `NaN` hoặc vô cực.
4. `parallelStream()` chưa có lý do hiệu năng; `sorted` là thao tác có trạng thái cần tổ chức dữ liệu toàn cục.
5. Nếu mục tiêu là top 3 sinh viên của **một khoa**, đoạn này còn thiếu `filter` trước `sorted`.
6. Dùng `String.compareTo` có thể không phù hợp yêu cầu tên tiếng Việt theo locale cụ thể.
7. `limit(3)` không tự bảo đảm `sorted` chỉ kiểm tra ba phần tử.

Bản sửa cho chính sách **top 3 toàn trường**:

~~~java
List<Student> corrected = students.stream()
    .sorted(PRIORITY_ORDER)
    .limit(3)
    .toList();

System.out.println(
    corrected.stream().map(Student::code).toList()
); // [S09, S02, S06]
~~~

Code dễ review hơn vì **quy tắc sắp xếp được đặt tên** và dùng chung trong các màn hình, thay vì lặp một biểu thức comparator dài có nguy cơ sai chỗ đảo chiều.

## 20. Checklist hoàn thành bài thực hành

| Câu hỏi kiểm tra | Dấu hiệu đạt |
|---|---|
| Đã định nghĩa **thứ tự ưu tiên các trường**? | GPA ↓, tín chỉ ↓, tên ↑, mã ↑ |
| Mỗi chiều sắp xếp được đảo **đúng phạm vi**? | Không có `reversed()` vô tình đảo cả chuỗi |
| Comparator có nhất quán và không phụ thuộc trạng thái ngoài? | Hàm chỉ đọc trường đã xác thực |
| Đầu vào có xử lý GPA `NaN` và vô cực? | Có chính sách từ chối/chuẩn hóa |
| Tên và mã có thể `null`? | Mô hình hoặc comparator xử lý rõ ràng |
| Danh sách nguồn có bị sửa ngoài ý muốn không? | Dùng `stream().sorted(...).toList()` |
| Top N có lọc đúng **trước khi** lấy giới hạn? | Pipeline phản ánh nghiệp vụ |
| Có test cho các trường hợp đồng GPA, đồng tín chỉ, đồng tên? | Test thứ tự S02/S06/S08 và S07/S03 |
| Có phân biệt **vị trí dòng** với **hạng đồng hạng**? | Chính sách rank được xác nhận riêng |
| Có cần sắp xếp tên theo tiếng Việt thực sự? | Chọn và kiểm thử collation theo yêu cầu |
| Có xử lý danh sách rỗng hoặc khoa không có người? | Trả List rỗng/Optional rỗng đúng nghĩa |
| Dữ liệu lớn có làm `sorted` tốn tài nguyên? | Đo trước khi tối ưu; cân nhắc top-k |
| Bật parallel có đủ lý do và kết quả vẫn đúng? | Test và benchmark trên workload đại diện |
| API kết quả có cam kết khả năng sửa List không? | Chọn `toList`/`toCollection` đúng yêu cầu |

## 21. Câu hỏi tự kiểm tra

1. `Stream.sorted(comparator)` có sửa List đầu vào không? — **Không**, nó tạo pipeline kết quả sắp xếp; List gốc không bị đổi thứ tự.
2. `Comparator.comparingDouble(Student::gpa).reversed()` ưu tiên điểm nào? — **GPA cao hơn**.
3. Vì sao nên dùng `thenComparing(Comparator.comparingInt(Student::credits).reversed())`? — Để đảo **riêng tiêu chí tín chỉ** mà không đảo lại GPA hoặc tiêu chí phía trước.
4. `thenComparing` chạy lúc nào? — Khi các tiêu chí trước so sánh bằng 0.
5. `Comparator.compare(a, b)` có buộc trả đúng `-1`, `0` hoặc `1` không? — **Không**, chỉ có dấu âm/0/dương là quan trọng.
6. Record `Student` có tự hỗ trợ `sorted()` không comparator không? — **Không**, record không mặc định triển khai `Comparable`.
7. `String.CASE_INSENSITIVE_ORDER` có bảo đảm xếp đúng theo ngôn ngữ tiếng Việt không? — **Không**; có thể cần collator theo locale.
8. `sorted().limit(3)` có chắc chỉ nhìn ba phần tử không? — **Không**, sắp xếp thường cần xem toàn bộ nguồn hữu hạn.
9. `filter(...).sorted().limit(5)` có cùng nghĩa `sorted().limit(5).filter(...)` không? — **Không**.
10. `Stream.toList()` trả List có thể gọi `add` không? — **Không**, danh sách kết quả không thể sửa.
11. `sorted` có loại trùng không? — **Không**, hai phần tử trùng vẫn được giữ.
12. `distinct` có mặc nhiên loại bản ghi trùng `code` không? — **Không**, nó dùng `equals`/`hashCode` của phần tử.
13. `min(PRIORITY_ORDER)` trả người ưu tiên thấp nhất hay cao nhất? — **Cao nhất**, vì comparator đưa người ưu tiên hơn về phía nhỏ hơn.
14. Một `HashSet` không có encounter order có bảo đảm thứ tự phần tử đồng hạng sau `sorted` không? — **Không** nếu comparator không phân biệt họ.
15. Có nên bật `parallelStream` cho 10 sinh viên mẫu để chắc chắn nhanh hơn không? — **Không**, chi phí phối hợp có thể vượt lợi ích.
16. Vì sao thêm mã sinh viên làm tiêu chí cuối? — Giúp kết quả hiển thị **xác định** giữa các bản ghi khác nhau nếu mã là duy nhất.

## 22. Tổng kết: ưu tiên quy tắc rõ hơn biểu thức ngắn

Bài toán sắp xếp danh sách sinh viên có nhiều tiêu chí không chỉ kiểm tra cú pháp `sorted`. Phần quan trọng là **chuyển quy tắc nghiệp vụ thành Comparator có thứ tự ưu tiên rõ ràng**, rồi bảo đảm dữ liệu và thao tác Stream thực sự tuân theo quy tắc đó.

Công thức cần nhớ:

~~~java
Comparator<Student> order =
    Comparator.comparingDouble(Student::gpa).reversed()
        .thenComparing(
            Comparator.comparingInt(Student::credits).reversed()
        )
        .thenComparing(
            Student::name,
            String.CASE_INSENSITIVE_ORDER
        )
        .thenComparing(Student::code);

List<Student> result = students.stream()
    .sorted(order)
    .toList();
~~~

Khi mở rộng ứng dụng, hãy kiểm tra **tie-breaker**, **null/GPA không hợp lệ**, **thứ tự lọc và giới hạn**, **định nghĩa rank**, **khả năng sửa đầu ra** và **chi phí của sắp xếp toàn cục**. Nếu cần nhóm theo khoa, dùng `groupingBy` với downstream sắp xếp; nếu chỉ cần một phần tử tốt nhất, cân nhắc `min` hoặc `max` thay vì sort toàn bộ.

Giữ các quy tắc này minh bạch giúp bạn xây pipeline Java Stream API chính xác, dễ bảo trì và dễ kiểm thử, đồng thời chuẩn bị cho các bài toán nâng cao về `collect`, collector tùy chỉnh, `Spliterator`, parallel Stream và Stream Gatherers.
