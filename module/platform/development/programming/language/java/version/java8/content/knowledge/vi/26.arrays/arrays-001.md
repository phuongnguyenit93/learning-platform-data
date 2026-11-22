# Arrays.parallelSort cho object và primitive trong Java 8+

## 1. Tổng quan: sắp xếp mảng mà vẫn tận dụng khả năng song song

**Arrays.parallelSort(...)** là nhóm phương thức của **java.util.Arrays** được giới thiệu từ **Java 8**, vẫn có mặt trong các bản Java hiện đại. Chúng sắp xếp mảng trực tiếp, có thể chia dữ liệu thành nhiều đoạn để xử lý song song, sau đó ghép kết quả thành một thứ tự thống nhất.

Nhu cầu thường gặp: sắp điểm thi dạng **int[]**, thời gian dạng **long[]**, giá trị đo dạng **double[]**, tên dạng **String[]**, hoặc object nghiệp vụ theo một hay nhiều trường. Cần hiểu đúng API trước khi chọn vì những mảng này có **kiểu phần tử** và **khả năng cung cấp Comparator** khác nhau.

Ba quy tắc cốt lõi:

1. **Arrays.parallelSort sửa ngay mảng truyền vào và trả void**, không tạo hay trả một mảng kết quả riêng.
2. **Primitive array** được sắp theo thứ tự định nghĩa của kiểu, còn **object array** có thể dùng natural ordering hoặc Comparator. **Object parallelSort được bảo đảm stable**.
3. Chữ **parallel** không bảo đảm nhanh hơn **Arrays.sort** trong mọi tình huống. Với mảng nhỏ, thư viện có thể dùng sắp xếp tuần tự; khi cần parallel tasks, nó sử dụng **ForkJoin common pool**.

Sau bài này, bạn có thể chọn overload chính xác; kiểm tra kết quả với số đặc biệt, null và phần tử có khóa bằng nhau; dùng đúng **[fromIndex, toIndex)**; tránh sửa nguồn khi muốn kết quả mới; và đánh giá hiệu năng mà không dựa vào những giả định không được API cam kết.

## 2. Những overload quan trọng

Các mảng primitive được hỗ trợ:

| Kiểu primitive | Gọi toàn mảng | Thứ tự |
| --- | --- | --- |
| byte[] | Arrays.parallelSort(byte[]) | Giá trị byte có dấu, tăng dần |
| short[] | Arrays.parallelSort(short[]) | Giá trị short có dấu, tăng dần |
| char[] | Arrays.parallelSort(char[]) | Giá trị char (UTF-16 code unit), tăng dần |
| int[] | Arrays.parallelSort(int[]) | Giá trị int, tăng dần |
| long[] | Arrays.parallelSort(long[]) | Giá trị long, tăng dần |
| float[] | Arrays.parallelSort(float[]) | Thứ tự số tăng dần với quy tắc NaN và signed zero |
| double[] | Arrays.parallelSort(double[]) | Tương tự float |

**Không có overload Arrays.parallelSort(boolean[])**. Java không áp đặt natural ordering cho boolean trong API này. Cũng không có overload truyền **Comparator** trực tiếp cho **int[]**, **long[]** hoặc các mảng primitive khác.

Với object array, các dạng tổng quát là:

~~~java
// Các phần tử có natural ordering tương thích (Comparable):
Arrays.parallelSort(objects);

// Có comparator do ứng dụng định nghĩa:
Arrays.parallelSort(objects, comparator);

// Chỉ sắp khoảng [fromIndex, toIndex):
Arrays.parallelSort(objects, fromIndex, toIndex);

// Sắp khoảng với comparator:
Arrays.parallelSort(objects, fromIndex, toIndex, comparator);
~~~

Đây là đoạn **minh họa các overload**; các biến objects, comparator, fromIndex và toIndex cần được khai báo ở nơi gọi. Mỗi kiểu primitive cũng có overload **parallelSort(array, fromIndex, toIndex)** tương ứng.

**Điểm phân biệt:** **int[]** chứa primitive int, còn **Integer[]** là array của object Integer. Vì Integer hỗ trợ Comparable, **Integer[]** có thể sắp tự nhiên và cũng có thể dùng một Comparator, chẳng hạn đảo thứ tự.

## 3. Sắp xếp primitive int[], long[] và các kiểu số nguyên

Mã ngắn:

~~~java
int[] scores = {30, 10, 20, 10};
Arrays.parallelSort(scores);
// scores: [10, 10, 20, 30]

long[] ids = {10L, -3L, 5L};
Arrays.parallelSort(ids);
// ids: [-3, 5, 10]
~~~

**Không có bước boxing** sang Integer/Long: phương thức làm việc trực tiếp với các phần tử primitive của mảng.

Với các kiểu nhỏ:

~~~java
byte[] a = {4, -2, 0};
Arrays.parallelSort(a);
// [-2, 0, 4]

short[] b = {100, -10, 20};
Arrays.parallelSort(b);
// [-10, 20, 100]

char[] c = {'z', 'A', 'b'};
Arrays.parallelSort(c);
// [A, b, z] theo giá trị char.
~~~

Mảng **char[]** được sắp theo giá trị **UTF-16 code unit**. Đây **không phải** một phép sắp xếp theo bảng chữ cái của tiếng Việt, tiếng Anh hay locale cụ thể; cũng không xử lý surrogate pairs như các ký tự Unicode có nghĩa trọn vẹn. Khi sắp **tên người, thành phố hoặc văn bản**, thường nên làm việc với String và bộ so sánh được thiết kế theo yêu cầu ngôn ngữ.

### Primitive muốn giảm dần thì sao?

Không biên dịch được cách viết:

~~~java
int[] values = {3, 1, 2};
// Arrays.parallelSort(values, Comparator.reverseOrder()); // Không có overload.
~~~

Nếu chỉ cần **int[] giảm dần**, hãy sắp tăng dần rồi đảo mảng tại chỗ:

~~~java
int[] values = {3, 1, 2};
Arrays.parallelSort(values);

for (int l = 0, r = values.length - 1; l < r; l++, r--) {
    int tmp = values[l];
    values[l] = values[r];
    values[r] = tmp;
}
// values = [3, 2, 1]
~~~

Cách khác là dùng **Integer[]**:

~~~java
Integer[] values = {3, 1, 2};
Arrays.parallelSort(values, Comparator.reverseOrder());
// [3, 2, 1]
~~~

Lựa chọn Integer[] có thêm chi phí wrapper/bộ nhớ; không nhất thiết đáng dùng nếu chỉ cần đảo một mảng primitive đã sắp.

## 4. float[] và double[]: NaN, Infinity, dấu của số 0

Với floating-point primitives, thứ tự tăng dần của **Arrays.parallelSort** có quy tắc cho những trường hợp đặc biệt:

- **-Infinity** nhỏ hơn các số hữu hạn.
- Các số hữu hạn được sắp tăng dần.
- **-0.0** đứng trước **+0.0**, dù khi so sánh primitive bằng **==**, hai số này được coi bằng nhau.
- **+Infinity** đứng sau tất cả các số hữu hạn.
- **NaN** được đặt sau mọi giá trị số, kể cả +Infinity.

Ví dụ đã kiểm chứng:

~~~java
double[] measurements = {
        Double.NaN, 0.0, -0.0, 3.5, -2.0
};

Arrays.parallelSort(measurements);

System.out.println(Arrays.toString(measurements));
// [-2.0, -0.0, 0.0, 3.5, NaN]
~~~

Mảng đã sắp không tự loại NaN hoặc đổi nghĩa của số âm 0. Khi dùng dữ liệu đo lường, các giá trị NaN/Infinity cần được xử lý theo quy tắc nghiệp vụ của phép tính thống kê tiếp theo.

Nếu sắp **Double[]** object theo custom comparator, dùng **Double.compare** hoặc **Comparator.comparingDouble(...)** thay vì tự trừ hai giá trị; phép trừ có thể gây sai quy tắc cho NaN và signed zero.

## 5. Object array với natural ordering

Mảng object không truyền Comparator dùng **natural ordering** của các phần tử. Kiểu phần tử cần triển khai **Comparable** thích hợp và các phần tử phải so sánh được lẫn nhau.

~~~java
String[] words = {"pear", "apple", "banana"};

Arrays.parallelSort(words);

System.out.println(Arrays.toString(words));
// [apple, banana, pear]
~~~

Với Integer[]:

~~~java
Integer[] numbers = {4, 1, 3};
Arrays.parallelSort(numbers);
// [1, 3, 4]
~~~

**String.compareTo** sắp theo thứ tự tự nhiên của chuỗi, không phải đối chiếu với các quy tắc collation của một ngôn ngữ người dùng. Nếu UI cần sắp chữ có dấu, hãy xây Comparator/Collator phù hợp và kiểm tra yêu cầu locale.

**Object không có Comparable:** nếu Student là một class/record không triển khai Comparable, viết **Arrays.parallelSort(students)** không phải lựa chọn đúng. Hãy cung cấp Comparator, chẳng hạn theo score, id hoặc timestamp.

## 6. Object array với Comparator do ứng dụng quyết định

Với dữ liệu Student có **id()** và **score()**, ta có thể sắp điểm giảm dần:

~~~java
Arrays.parallelSort(
        students,
        Comparator.comparingInt(Student::score).reversed());
~~~

**Comparator.comparingInt** đọc một trường int, tránh boxing để so từng khóa. **reversed()** đảo kết quả so sánh; không cần viết phép trừ.

Muốn điểm giảm nhưng cùng điểm thì id tăng:

~~~java
Comparator<Student> byScoreThenId =
        Comparator.comparingInt(Student::score)
                  .reversed()
                  .thenComparing(Student::id);

Arrays.parallelSort(students, byScoreThenId);
~~~

Đây là cách định nghĩa **nhiều khóa so sánh**, không phụ thuộc thứ tự ban đầu để xử lý trường hợp cùng điểm.

Với chuỗi có thể null:

~~~java
String[] names = {"Bob", null, "Alice"};

Arrays.parallelSort(
        names,
        Comparator.nullsLast(Comparator.naturalOrder()));

// [Alice, Bob, null]
~~~

**Comparator.nullsFirst/nullsLast** có từ Java 8. Chúng chỉ phù hợp khi nghiệp vụ cho phép null là phần tử được sắp xếp. Nếu null là dữ liệu lỗi, nên validate hoặc lọc bỏ trước.

## 7. Stable sorting trên object: bảo đảm chính thức

Java API bảo đảm các overload **parallelSort dành cho object** là **stable**: phần tử được coi là bằng nhau theo phép so sánh vẫn giữ nguyên **thứ tự tương đối** sau sắp xếp.

Ví dụ ban đầu:

| Thứ tự ban đầu | Student | Score |
| ---: | --- | ---: |
| 1 | S1 | 90 |
| 2 | S2 | 80 |
| 3 | S3 | 90 |
| 4 | S4 | 80 |

Khi chỉ sắp theo score giảm dần, kết quả là:

~~~text
S1, S3, S2, S4
~~~

**S1 và S3** cùng điểm 90 nên giữ thứ tự S1 trước S3. **S2 và S4** cùng điểm 80 nên giữ S2 trước S4. Toàn bộ thứ tự đã đạt yêu cầu score giảm.

**Stable không có nghĩa Java ngầm hiểu id.** Nếu comparator chỉ dùng score, ổn định được xét ở giá trị compare == 0. Nếu muốn đổi thứ tự id trong một nhóm cùng điểm, thêm quy tắc thứ cấp bằng **thenComparing**.

Với **primitive**, hai phần tử cùng giá trị không có id/trường phụ để phân biệt đã đổi thứ tự tương đối. Do đó bảo đảm ổn định có ý nghĩa thực tế nổi bật nhất khi sắp các object có nhiều thuộc tính.

## 8. Chỉ sắp một đoạn: [fromIndex, toIndex)

Overload có chỉ số tuân theo khoảng **nửa mở**:

- **fromIndex**: inclusive, bao gồm vị trí này.
- **toIndex**: exclusive, không bao gồm vị trí này.
- Các phần tử ngoài khoảng giữ nguyên vị trí.

~~~java
int[] a = {50, 9, 2, 8, 1, 60};

Arrays.parallelSort(a, 1, 5);

// Chỉ index 1,2,3,4 được sắp.
// a = [50, 1, 2, 8, 9, 60]
~~~

Khoảng ban đầu có các giá trị [9, 2, 8, 1], sắp tăng dần thành [1, 2, 8, 9], nên phần tử tại index 0 và index 5 không bị di chuyển.

Object array cũng có overload đoạn:

~~~java
String[] words = {"Z", "pear", "apple", "banana", "Y"};
Arrays.parallelSort(words, 1, 4);
// [Z, apple, banana, pear, Y]
~~~

Nếu cần Comparator:

~~~java
Arrays.parallelSort(
        students, 1, students.length,
        Comparator.comparingInt(Student::score));
~~~

Đoạn trên là **mã minh họa** cần biến students và kiểu Student đã được định nghĩa. Vị trí 0 được giữ nguyên, các vị trí 1 đến cuối được sắp theo score tăng.

### Kiểm tra cận đúng

~~~text
0 <= fromIndex <= toIndex <= array.length
~~~

- **fromIndex == toIndex**: khoảng rỗng hợp lệ.
- **fromIndex > toIndex**: **IllegalArgumentException**.
- **fromIndex < 0** hoặc **toIndex > array.length**: **ArrayIndexOutOfBoundsException**.
- **array == null**: **NullPointerException** khi thao tác với mảng.

Dùng **[0, array.length)** nếu muốn cả mảng. Không nhầm cận trên với chỉ số phần tử cuối (array.length - 1).

## 9. Arrays.parallelSort sửa nguồn, không trả mảng mới

Tất cả overload **parallelSort trả void**. Vì vậy:

~~~java
int[] original = {9, 3, 7, 1};

// Sai kiểu: không thể gán kết quả void vào int[].
// int[] sorted = Arrays.parallelSort(original);

Arrays.parallelSort(original);
// original đã bị sửa thành [1, 3, 7, 9].
~~~

Nếu muốn đầu vào vẫn nguyên, hãy tạo **clone** trước:

~~~java
int[] original = {9, 3, 7, 1};
int[] sorted = original.clone();

Arrays.parallelSort(sorted);

// original: [9, 3, 7, 1]
// sorted:   [1, 3, 7, 9]
~~~

Các biến khác cùng tham chiếu đến một mảng sẽ quan sát kết quả sau khi sort. **sorted = original** chỉ là alias, không tạo bản sao.

Với object array, **clone()** là shallow copy: tạo mảng mới nhưng giữ tham chiếu tới **cùng các object phần tử**. Sort bản sao không hoán vị các vị trí của mảng nguồn, tuy nhiên thay đổi trạng thái của một object mutable có thể được cả hai mảng quan sát.

Nếu chỉ muốn một đoạn bản sao:

~~~java
int[] original = {50, 9, 2, 8, 1, 60};
int[] part = Arrays.copyOfRange(original, 1, 5);
Arrays.parallelSort(part);

// part = [1, 2, 8, 9]
// original không bị sửa.
~~~

**In-place không đồng nghĩa không dùng bộ nhớ phụ.** Implementation sort-merge song song có thể cấp vùng tạm để ghép các đoạn; việc sort sửa trực tiếp mảng đầu ra không phải lời hứa thuật toán luôn O(1) memory.

## 10. Chương trình Java 17 độc lập, chạy và kiểm chứng kết quả

Tạo tệp **ParallelSortArraysDemo.java**:

~~~java
import java.util.*;
import java.util.stream.*;

public class ParallelSortArraysDemo {
    record Student(String id, int score) {}

    public static void main(String[] args) {
        int[] numbers = {9, 3, 7, 1, 5};
        int[] untouched = numbers.clone();
        Arrays.parallelSort(numbers);
        System.out.println("primitive int: " + Arrays.toString(numbers));
        System.out.println("original copy: " + Arrays.toString(untouched));

        long[] ids = {10L, -3L, 5L};
        Arrays.parallelSort(ids);
        System.out.println("primitive long: " + Arrays.toString(ids));

        double[] measures = {
                Double.NaN, 0.0, -0.0, 3.5, -2.0
        };
        Arrays.parallelSort(measures);
        System.out.println("primitive double: " + Arrays.toString(measures));

        char[] letters = {'z', 'A', 'b'};
        Arrays.parallelSort(letters);
        System.out.println("primitive char: " + Arrays.toString(letters));

        String[] words = {"pear", "apple", "banana"};
        Arrays.parallelSort(words);
        System.out.println("natural objects: " + Arrays.toString(words));

        Student[] students = {
                new Student("S1", 90),
                new Student("S2", 80),
                new Student("S3", 90),
                new Student("S4", 80)
        };
        Arrays.parallelSort(
                students,
                Comparator.comparingInt(Student::score).reversed());

        String[] sortedIds = Arrays.stream(students)
                .map(Student::id)
                .toArray(String[]::new);
        System.out.println(
                "stable student ids: " + Arrays.toString(sortedIds));

        int[] partial = {50, 9, 2, 8, 1, 60};
        Arrays.parallelSort(partial, 1, 5);
        System.out.println("range [1,5): " + Arrays.toString(partial));

        String[] withNull = {"Z", null, "a"};
        Arrays.parallelSort(
                withNull,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
        System.out.println("nulls last: " + Arrays.toString(withNull));

        Integer[] wrappers = {4, 1, 3};
        Arrays.parallelSort(wrappers);
        System.out.println("boxed integers: " + Arrays.toString(wrappers));

        try {
            Arrays.parallelSort(new int[3], 2, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad range: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac ParallelSortArraysDemo.java
java ParallelSortArraysDemo
~~~

**Đầu ra chính xác đã kiểm chứng bằng Java 17-compatible compiler:**

~~~text
primitive int: [1, 3, 5, 7, 9]
original copy: [9, 3, 7, 1, 5]
primitive long: [-3, 5, 10]
primitive double: [-2.0, -0.0, 0.0, 3.5, NaN]
primitive char: [A, b, z]
natural objects: [apple, banana, pear]
stable student ids: [S1, S3, S2, S4]
range [1,5): [50, 1, 2, 8, 9, 60]
nulls last: [a, Z, null]
boxed integers: [1, 3, 4]
bad range: IllegalArgumentException
~~~

**Lưu ý phiên bản:** record Student là cú pháp chính thức từ Java 16; chương trình đầy đủ dùng Java 17+. Bản thân **Arrays.parallelSort**, **Comparator.comparingInt**, **Comparator.nullsLast** đều có từ Java 8. Nếu dự án giới hạn JDK 8, thay record bằng class có constructor và hai phương thức id()/score() tương ứng.

Chương trình dùng mảng nhỏ để kiểm tra tính đúng và hiện tượng stable. Nó **không** phải benchmark để chứng minh tốc độ.

## 11. Phân tích kết quả chương trình

| Dòng in | Điều được xác nhận |
| --- | --- |
| primitive int | int[] sắp tăng và mảng nguồn bị sửa |
| original copy | bản sao được tạo trước vẫn có thứ tự cũ |
| primitive long | sắp giá trị long có dấu |
| primitive double | NaN ở cuối, -0.0 trước 0.0 |
| primitive char | sắp theo giá trị char |
| natural objects | String dùng Comparable/natural order |
| stable student ids | cùng score giữ thứ tự tương đối |
| range [1,5) | chỉ vị trí 1 đến 4 được sắp |
| nulls last | Comparator chủ động xử lý phần tử null |
| boxed integers | Integer[] hỗ trợ object overload |
| bad range | fromIndex > toIndex gây IllegalArgumentException |

Không suy ra thời điểm mapper/comparator được chạy từ thứ tự dòng in: chương trình chỉ in **sau** khi mỗi lần parallelSort đã hoàn tất. Những so sánh nội bộ có thể được thực thi song song tùy kích thước và runtime.

## 12. Comparator hợp lệ quan trọng hơn mức song song

Một **Comparator** cần tạo thứ tự nhất quán, đặc biệt phải đáp ứng tính bắc cầu và quy tắc so sánh đối xứng về dấu. Với kiểu số nguyên, tránh tự dùng phép trừ:

~~~java
Comparator<Integer> bad = (a, b) -> a - b;
// Có thể overflow khi a và b ở hai đầu miền int.

Comparator<Integer> good = Integer::compare;
~~~

Với Student có điểm số int:

~~~java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
~~~

**Đừng dùng comparator ngẫu nhiên hoặc phụ thuộc biến mutable bị thay đổi trong lúc sort.** Khi parallelSort chia việc, comparator có thể được gọi đồng thời từ nhiều worker, nên shared mutable state thiếu đồng bộ có thể gây race và khiến thứ tự không nhất quán.

Ví dụ phản tác dụng:

~~~java
int[] counter = {0};

Comparator<Student> unsafe = (a, b) -> {
    counter[0]++; // Side effect trên bộ đếm dùng chung.
    return Integer.compare(a.score(), b.score());
};
~~~

Đây là **phản ví dụ**, không phải code nên đưa vào production. Hãy dùng comparator thuần và công cụ profiling riêng nếu muốn biết chi phí so sánh.

**Nếu comparator vi phạm hợp đồng**, implementation **có thể** phát hiện và ném IllegalArgumentException, nhưng không có bảo đảm mọi lỗi đều được phát hiện. Hãy unit test comparator với các giá trị biên, bằng nhau, min/max và chuỗi null nếu có.

## 13. Lỗi với null, Comparable và exception

### Null khi sắp object array

Với natural ordering, phần tử null không có compareTo nên có thể gây **NullPointerException**. Nếu null là dữ liệu hợp lệ, chọn **Comparator.nullsFirst** hoặc **Comparator.nullsLast**. Nếu null không hợp lệ, validate trước sort để báo lỗi có ngữ cảnh.

### Object không có natural ordering

Một class không triển khai Comparable không thể được sắp tự nhiên chỉ bằng Arrays.parallelSort(objectArray) theo kiểu API generic phù hợp. Hãy dùng overload nhận Comparator. Nếu đối tượng trong phạm vi không thể so sánh với nhau, có thể gặp **ClassCastException**.

### Sai khoảng chỉ số

- **IllegalArgumentException** khi fromIndex > toIndex.
- **ArrayIndexOutOfBoundsException** khi fromIndex âm hoặc toIndex lớn hơn array.length.
- **NullPointerException** khi mảng đầu vào null.

### Nếu sort thất bại giữa chừng

**Arrays.parallelSort không có hợp đồng transaction/rollback.** Nếu comparator ném exception hoặc dữ liệu bị sửa đồng thời, đừng dựa vào việc mảng vẫn nguyên trạng. Khi dữ liệu gốc phải được giữ an toàn, hãy clone/copy, sort bản sao, rồi chỉ công bố kết quả nếu hoàn thành thành công.

## 14. Arrays.sort và Arrays.parallelSort: điểm giống và khác

| Tiêu chí | Arrays.sort | Arrays.parallelSort |
| --- | --- | --- |
| Sửa mảng nhận vào | Có | Có |
| Trả mảng mới | Không, trả void | Không, trả void |
| Mảng primitive | Có | Có |
| Object natural order và Comparator | Có | Có |
| Object sort stable | Có | Có |
| Song song hóa sắp xếp | Không phải mục tiêu API | Có thể chia việc để dùng nhiều worker |
| Trường hợp mảng nhỏ | Thường có overhead thấp | Có thể dùng sort tuần tự thay vì chia việc |
| Bộ nhớ tạm | Phụ thuộc thuật toán/kiểu mảng | Parallel merge có thể cần thêm vùng làm việc tạm |

**Arrays.parallelSort không cam kết nhanh hơn Arrays.sort.** Việc chia/ghép, cấp phát vùng làm việc, cạnh tranh common pool và lịch CPU có thể khiến kết quả ngược lại trên mảng nhỏ hoặc hệ thống đang tải nặng.

Tài liệu Arrays mô tả **parallel sort-merge**: chia mảng thành những đoạn, sắp từng đoạn bằng phương thức thích hợp khi đủ nhỏ, rồi gộp. Parallel tasks dùng **ForkJoin common pool**. Đừng dựa vào một ngưỡng nội bộ cố định để thiết kế correctness vì chi tiết triển khai có thể thay đổi giữa các phiên bản JDK.

## 15. Mảng nguồn và Stream.sorted là hai mô hình khác nhau

Khi muốn trực tiếp sửa mảng hiện có:

~~~java
int[] a = {3, 1, 2};
Arrays.parallelSort(a);
// a = [1, 2, 3]
~~~

Khi muốn kết quả mới từ pipeline:

~~~java
int[] a = {3, 1, 2};

int[] sorted = Arrays.stream(a)
        .sorted()
        .toArray();

// a = [3, 1, 2]
// sorted = [1, 2, 3]
~~~

Ở ví dụ Stream, **Arrays.stream(int[])** trả IntStream, **sorted()** là intermediate operation và **toArray()** materialize mảng mới. Đừng nhầm **Arrays.parallelSort(a)** với **Arrays.stream(a).parallel().sorted().toArray()**: đoạn thứ hai trả kết quả mới, còn đoạn đầu sửa mảng.

Với object:

~~~java
String[] words = {"pear", "apple", "banana"};

String[] sorted = Arrays.stream(words)
        .sorted()
        .toArray(String[]::new);
~~~

Object Stream có overload **sorted(Comparator)**. **List.sort** là mutator của List, không phải phương thức của mảng.

Nếu chỉ cần sort một đoạn mà giữ nguyên nguồn, **Arrays.copyOfRange** rồi **parallelSort** rõ ràng hơn việc dựng một pipeline phức tạp.

## 16. Hiệu năng và ForkJoin common pool

Song song hóa không miễn phí. ParallelSort có thể phân chia nhiều đoạn, chạy công việc trên ForkJoin workers, rồi gộp kết quả. Tài liệu API mô tả việc dùng **ForkJoin common pool** cho các tác vụ song song và fallback sang sắp xếp tuần tự với dữ liệu nhỏ.

Những yếu tố chi phối:

1. **Kích thước mảng** — quá nhỏ không đủ việc để vượt overhead điều phối.
2. **Số lõi/CPU thực tế** — máy ít lõi, bị giới hạn CPU hoặc đang tải nặng có thể không hưởng lợi.
3. **Phân bố dữ liệu** — gần sắp, đảo ngược, nhiều phần tử trùng hay ngẫu nhiên có hành vi hiệu năng khác.
4. **Chi phí comparator** — nhiều field hoặc xử lý phức tạp làm số phép so sánh tốn thời gian hơn.
5. **Vùng nhớ tạm/GC** — thuật toán song song có thể cần bộ đệm ghép; mảng object có nhiều tham chiếu có chi phí riêng.
6. **Cạnh tranh common pool** — những tác vụ Parallel Stream hoặc CompletableFuture async mặc định khác có thể dùng chung worker.

**Không gọi HTTP, JDBC, sleep hoặc lock kéo dài trong Comparator.** Đây không phải cách làm sorting scalable: comparator có thể được gọi rất nhiều lần và có nguy cơ giữ worker của common pool. Nếu phải lấy dữ liệu ngoài làm khóa sắp xếp, hãy tải và chuẩn bị khóa **trước** rồi sort với comparator thuần.

**Arrays.parallelSort là lời gọi đồng bộ từ góc nhìn người gọi**: phương thức trả về khi sắp xếp xong (hoặc ném exception), dù bên trong có task song song. Nó không trả Future và không tự động trở thành non-blocking API.

### Đo để quyết định

Sử dụng dữ liệu đại diện và tạo bản sao tương đương cho hai phép thử:

- Chạy Arrays.sort trên một bản sao và Arrays.parallelSort trên bản sao khác.
- Không benchmark bằng cách chạy lần thứ hai trên mảng đã được lần thứ nhất sắp xếp.
- Warm-up JVM và lặp lại nhiều lượt; quan sát GC, CPU, bộ nhớ và latency.
- Dùng JMH hoặc công cụ benchmark tin cậy khi hiệu năng là yêu cầu quan trọng.
- Đảm bảo kết quả có thứ tự đúng và là permutation của dữ liệu nguồn.

**Không tự công bố một con số N cố định** mà tại đó parallelSort luôn thắng: ngưỡng thực tế thay đổi theo máy, JDK, comparator và dữ liệu.

## 17. An toàn đồng thời và ownership của mảng

Arrays.parallelSort sửa **một object mảng có thể bị nhiều tham chiếu chia sẻ**. Không để thread khác đồng thời thay đổi mảng khi sort đang chạy; không để reader sử dụng dữ liệu đang được hoán vị mà thiếu phối hợp đúng.

Với object array, còn cần bảo đảm **trạng thái dùng để so sánh không bị thay đổi** trong khi sort. Nếu điểm Student là mutable và thread khác thay đổi score liên tục, một comparator dù viết đúng cũng có thể quan sát dữ liệu không nhất quán.

Các lựa chọn thực tế:

- **Ownership riêng:** module xử lý sở hữu mảng và độc quyền thay đổi nó trong suốt thời gian sort.
- **Snapshot:** clone/copy mảng rồi sort, công bố bản đã hoàn tất.
- **Dữ liệu phần tử bất biến:** record/immutable DTO giúp comparator không thấy giá trị thay đổi ngoài ý muốn.
- **Đồng bộ phù hợp:** nếu cấu trúc bị chia sẻ cho nhiều thread và cần cập nhật, thiết kế điểm giao nhận rõ thay vì để việc đọc/sắp xảy ra đồng thời tự do.

Sắp xếp trên array clone vẫn chỉ là **shallow copy** của các object phần tử; không thay thế yêu cầu immutable data nếu giá trị trong object cũng có thể bị sửa.

## 18. Checklist kiểm thử tính đúng

Một bộ kiểm tra có ích nên bao gồm:

| Dữ liệu thử | Mong muốn |
| --- | --- |
| Mảng rỗng | Xử lý hợp lệ, kết quả vẫn rỗng |
| Mảng một phần tử | Không thay đổi |
| Mảng đã sắp | Vẫn có thứ tự đúng |
| Mảng đảo ngược | Trở thành thứ tự tăng hoặc theo comparator |
| Nhiều giá trị trùng | Không mất phần tử; với object, stable nếu compare == 0 |
| Giá trị cực trị int/long | Comparator không tràn, kết quả đúng |
| double NaN, -0.0, +0.0 | Quy tắc thứ tự đặc biệt được tôn trọng |
| Null trong object[] | Có chính sách validate hoặc comparator xử lý null |
| Khoảng [1,5) | Phần tử ngoài đoạn giữ nguyên |
| Chỉ số sai | Exception đúng loại |
| Mảng object clone | Vị trí của mảng nguồn không bị hoán vị |
| Comparator nhiều khóa | Tie-breaker hoạt động theo yêu cầu |

Với dữ liệu lớn, có thể kiểm tra tính **sorted** theo comparator và tính **permutation** bằng một tập test nhỏ có oracle đáng tin; đừng chỉ nhìn vài phần tử đầu/cuối. Với stable object sort, cần ghi nhớ thứ tự ban đầu của các phần tử có cùng khóa.

## 19. Luyện tập có lời giải

### Bài 1 — Sắp tăng primitive mà vẫn giữ bản gốc

~~~java
int[] source = {7, 2, 9};
int[] result = source.clone();

Arrays.parallelSort(result);

// source = [7, 2, 9]
// result = [2, 7, 9]
~~~

Giải thích: phép sắp chỉ sửa result. **Clone** tạo mảng mới trước khi gọi.

### Bài 2 — Sắp điểm giảm với object

~~~java
Arrays.parallelSort(
        students,
        Comparator.comparingInt(Student::score).reversed());
~~~

Giải thích: chọn overload object với comparator. Các Student cùng điểm giữ thứ tự tương đối ban đầu nhờ stable sort. Nếu muốn cùng điểm xếp id tăng, thêm thenComparing(Student::id).

### Bài 3 — Khoảng chỉ số exclusive

~~~java
int[] a = {5, 9, 1, 3, 8};
Arrays.parallelSort(a, 1, 4);
// [5, 1, 3, 9, 8]
~~~

Index 1, 2, 3 được sắp; index 0 và 4 giữ nguyên.

### Bài 4 — Muốn int[] giảm dần bằng Comparator?

Không có overload **parallelSort(int[], Comparator)**. Có thể sort tăng rồi đảo mảng, hoặc sử dụng **Integer[]** nếu thật sự cần comparator và chấp nhận chi phí wrapper.

### Bài 5 — Có một phần tử null trong String[]

~~~java
String[] names = {"B", null, "A"};

Arrays.parallelSort(
        names, Comparator.nullsLast(Comparator.naturalOrder()));

// [A, B, null]
~~~

Chọn comparator để null có vị trí rõ; nếu null là dữ liệu sai, nên validate thay vì che lỗi.

### Bài 6 — Stable nghĩa là sao khi hai object cùng score?

Comparator theo score trả 0 khi bằng điểm. Với object sort stable, những object ấy giữ thứ tự tương đối từ mảng gốc; stable không tự ưu tiên id nếu id không có trong comparator.

### Bài 7 — ParallelSort có luôn dùng nhiều thread?

Không. Mảng nhỏ có thể dùng phương pháp sắp tuần tự. Khi phải tạo task song song, implementation dùng common pool; hiệu năng chịu ảnh hưởng kích thước, dữ liệu và mức tải.

### Bài 8 — Comparator ném exception thì mảng có chắc nguyên trạng?

Không. Đây là một mutator, không phải transaction có rollback. Khi nguồn phải được bảo toàn, hãy clone/copy và sort trên bản sao trước khi công bố nó.

## 20. Ghi nhớ và tài liệu đang áp dụng

1. **Arrays.parallelSort (Java 8+)** vẫn là API hiện hành; sắp trực tiếp mảng primitive hoặc object, trả **void**.
2. Primitive hỗ trợ **byte, short, char, int, long, float, double**, không hỗ trợ boolean[] và không có comparator overload.
3. Object có natural ordering qua Comparable hoặc Comparator; **object parallelSort được bảo đảm stable**.
4. Khoảng index là **[fromIndex, toIndex)**; cận trên exclusive.
5. float/double có thứ tự đặc biệt: **-0.0 đứng trước +0.0**, **NaN ở cuối**.
6. Muốn giữ nguyên mảng nguồn, hãy clone/copy trước; object array clone chỉ sao chép nông.
7. **Arrays.parallelSort không luôn nhanh hơn Arrays.sort**; các tác vụ song song dùng common pool và có thể cần vùng nhớ tạm.
8. Comparator cần nhất quán, thuần, thread-safe và tránh các phép trừ có nguy cơ overflow.
9. Chọn **Stream.sorted + toArray** khi cần tạo kết quả mới, thay vì sửa mảng hiện có.
10. Kiểm chứng cả tính đúng, phạm vi sắp, độ ổn định object, thời gian và mức sử dụng tài nguyên trước khi tối ưu.

### Tài liệu chính thức

- **Java SE 26 — java.util.Arrays**, các overload parallelSort, stable object sort, algorithm, common pool: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html
- **Java SE 26 — Comparator**, comparingInt, reversed, thenComparing, nullsFirst/nullsLast và hợp đồng so sánh: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html
- **Java SE 26 — ForkJoinPool**, common pool và tài nguyên song song: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **Java SE 26 — Stream/IntStream**, sorted và toArray khi cần tạo mảng kết quả: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html

**Tương thích phiên bản:** mã chạy độc lập dùng **record Student**, nên cần JDK 17+; bản thân **Arrays.parallelSort**, **Comparator.comparingInt**, **Comparator.nullsLast** đã có trong Java 8 và vẫn áp dụng ở Java hiện hành.
