# sorted() theo thứ tự tự nhiên hoặc Comparator trong Java Stream

## 1. Mục tiêu

Khi xử lý dữ liệu bằng Java Stream, **sorted()** cho phép tạo ra một luồng phần tử được **sắp xếp theo thứ tự** trước khi đưa tới terminal operation. Có hai hình thức quan trọng:

- **sorted() không tham số**: dùng **thứ tự tự nhiên (natural order)** do phần tử cung cấp qua **Comparable**.
- **sorted(Comparator)**: dùng một **quy tắc so sánh do caller truyền vào**, phù hợp khi cần sắp theo nhiều trường, giảm dần, xử lý null hoặc có nhiều cách sắp cùng một kiểu dữ liệu.

Sau bài này, bạn có thể đọc và viết cả hai overload, hiểu comparator trả số âm/0/dương, xây các tiêu chí bằng comparing/thenComparing/reversed, biết khi nào sắp xếp giữ thứ tự ban đầu của phần tử bằng nhau, nhận diện đặc tính **lazy nhưng stateful** của sorted, tránh làm thay đổi nguồn và xử lý các lỗi thường gặp với null, generic, tràn số và parallel stream.

## 2. sorted() nằm ở đâu trong pipeline?

Cấu trúc một pipeline:

~~~java
List<Integer> result = List.of(4, 1, 3, 2)
        .stream()
        .sorted()
        .toList();
~~~

**Kết quả:** [1, 2, 3, 4].

Các bước:

1. **List.of(...).stream()** tạo Stream từ danh sách nguồn.
2. **sorted()** tạo một **intermediate operation**, mô tả yêu cầu đưa phần tử ra theo thứ tự tăng dần.
3. **toList()** là terminal operation, kích hoạt pipeline để tạo kết quả.

**sorted là intermediate operation lazy:** việc gọi sorted() đơn thuần chưa nhất thiết đọc toàn bộ nguồn hoặc gọi comparator. Nhưng nó đồng thời là **stateful operation**: khi được đánh giá, sắp xếp tổng quát thường cần đệm nhiều hoặc tất cả phần tử trước khi bắt đầu phát ra phần tử đầu tiên đúng thứ tự.

Sơ đồ:

~~~text
List nguồn
   |
   v
stream() --> filter(...) --> sorted(comparator) --> limit(3)
                                           |
                                           v
                                         toList()
                                           |
                                           v
                                   List kết quả theo thứ tự
~~~

Không nên xem sorted là một lời gọi **sửa danh sách ngay tại chỗ**. Nó tạo một Stream mới về mặt chuỗi thao tác; danh sách nguồn không bị sort trực tiếp nếu callback và những tác vụ khác không can thiệp.

## 3. Hai overload của Stream.sorted

Các chữ ký rút gọn:

~~~java
Stream<T> sorted()

Stream<T> sorted(Comparator<? super T> comparator)
~~~

Cùng trả một Stream<T>: sorted **đổi thứ tự**, không đổi kiểu phần tử.

| Hình thức | Quy tắc | Điều kiện quan trọng |
| --- | --- | --- |
| **sorted()** | Thứ tự tự nhiên | Các phần tử phải so sánh được theo Comparable thích hợp |
| **sorted(comparator)** | Thứ tự do Comparator quyết định | Comparator tương thích với T và tuân thủ hợp đồng so sánh |
| **IntStream.sorted()** | Thứ tự số nguyên tăng dần | Primitive int; không có overload Comparator cho IntStream |
| **LongStream.sorted()** | Thứ tự long tăng dần | Primitive long |
| **DoubleStream.sorted()** | Thứ tự double theo phép so sánh được quy định | Cần hiểu NaN, +0.0/-0.0 nếu dữ liệu có các trường hợp đó |

Chữ ký **Comparator<? super T>** có nghĩa comparator có thể nhận T **hoặc một supertype của T**, bởi comparator sẽ tiêu thụ hai giá trị T trong mỗi lời so sánh. Ví dụ **Comparator<Animal>** có thể so sánh các **Dog**, nếu Dog là subtype của Animal và comparator đọc các thuộc tính chung trên Animal.

## 4. sorted() và Comparable: thứ tự tự nhiên

**Comparable<T>** nằm trong java.lang và có phương thức:

~~~java
int compareTo(T other);
~~~

Một số kiểu Java đã định nghĩa thứ tự tự nhiên:

- **Integer**, **Long**: thứ tự số tăng dần.
- **String**: so sánh từ điển theo các đơn vị UTF-16 của chuỗi, có phân biệt chữ hoa/chữ thường; không tự đồng nghĩa với quy tắc bảng chữ cái của một locale.
- **LocalDate**: thứ tự ngày tháng.
- **BigDecimal**: thứ tự giá trị số theo compareTo; cần lưu ý compareTo và equals có thể không nhất quán với các giá trị khác scale.
- **Enum**: thứ tự khai báo hằng enum.

Ví dụ:

~~~java
List<String> languages =
        List.of("Java", "Go", "Kotlin", "C", "java");

List<String> sorted = languages.stream()
        .sorted()
        .toList();

System.out.println(sorted);
// [C, Go, Java, Kotlin, java]
~~~

**"Java"** đứng trước **"java"** vì String natural order phân biệt hoa và thường. Muốn sắp theo quy tắc ngôn ngữ cụ thể, có thể dùng một **Collator** cấu hình cho locale thích hợp dưới dạng Comparator; không nên nghĩ sorted() của String đã xử lý hết các đặc thù ngôn ngữ.

### 4.1. Lớp tự định nghĩa chưa có thứ tự tự nhiên

Giả sử có:

~~~java
record Product(String code, long priceVnd) { }
~~~

Một Product record **không tự implement Comparable<Product>**. Vì vậy một Stream<Product> gọi **sorted() không Comparator** có thể ném **ClassCastException** khi terminal operation thực sự cần so sánh phần tử. Không được cho rằng record tự sắp được theo các field.

Nếu dữ liệu nghiệp vụ có **một thứ tự tự nhiên thật sự và ổn định**, có thể cho lớp implement Comparable với compareTo phù hợp. Nhưng nhiều lớp như Order, Product, Employee có **nhiều tiêu chí hợp lệ**, nên truyền Comparator thường linh hoạt và ít gắn chặt thứ tự vào mô hình hơn.

### 4.2. Không phải cứ viết sorted() là exception nổ ngay

Do Stream lazy, lỗi do các phần tử không Comparable thường chỉ xuất hiện **khi terminal yêu cầu đánh giá đến phép so sánh cần thiết**. Với nguồn rỗng hoặc một phần tử, triển khai có thể không cần một phép compare cụ thể.

**Thiết kế đúng:** bảo đảm kiểu phần tử và quy tắc so sánh hợp lệ trước khi xây pipeline; không dựa vào thời điểm exception để kiểm tra khả năng Comparable.

## 5. sorted(Comparator): chọn quy tắc theo mục đích

**Comparator<T>** nằm trong java.util, là functional interface có SAM:

~~~java
int compare(T left, T right);
~~~

Ý nghĩa dấu của kết quả:

- **Âm**: left đứng trước right.
- **0**: left và right **tương đương về thứ tự theo comparator**.
- **Dương**: left đứng sau right.

Không bắt buộc chỉ trả -1, 0, +1; chỉ **dấu** là trọng tâm. Ví dụ:

~~~java
Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending = (a, b) ->
        Integer.compare(b, a);

System.out.println(ascending.compare(2, 5) < 0); // true
System.out.println(descending.compare(2, 5) > 0); // true
~~~

Comparator có thể được viết bằng lambda, method reference hoặc các factory method của Comparator. Dùng comparator để diễn đạt **“so theo thuộc tính nào, theo chiều nào, xử lý bằng nhau như thế nào”**.

### 5.1. Tránh trừ hai số khi so sánh

~~~java
// Không an toàn nếu int bị tràn:
// Comparator<Integer> bad = (a, b) -> a - b;

Comparator<Integer> safe = Integer::compare;
~~~

Nếu **a = Integer.MAX_VALUE** và **b = -1**, phép a-b có thể bị tràn int, làm dấu của kết quả sai. Integer.compare xử lý đúng quan hệ thứ tự. Với long, dùng **Long.compare** hoặc **Comparator.comparingLong** thay vì ép hiệu về int.

Khi so sánh double, **Double.compare** có quy tắc cho NaN và -0.0/+0.0; nếu nghiệp vụ không mong muốn những giá trị đó, cần validation hoặc tiêu chí rõ ràng.

## 6. Comparator.comparing và các biến thể primitive

Khi muốn sắp đối tượng theo một field, Java có các factory method:

~~~java
Comparator<Employee> byName =
        Comparator.comparing(Employee::name);

Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> bySalary =
        Comparator.comparingLong(Employee::salary);
~~~

Đây là các đoạn minh họa giả sử Employee có các accessor tương ứng, không phải chương trình độc lập. **comparingInt/comparingLong/comparingDouble** giúp lấy khóa nguyên thủy mà không bắt buộc boxing kiểu khóa trong SAM.

Dùng với Stream:

~~~java
List<Employee> ascendingByAge = employees.stream()
        .sorted(Comparator.comparingInt(Employee::age))
        .toList();
~~~

Sự khác nhau:

- **Comparator.comparing(Employee::name)**: tạo comparator theo một khóa tham chiếu vốn có thứ tự tự nhiên, thường là String.
- **Comparator.comparingInt(Employee::age)**: tạo comparator theo khóa int.
- **Comparator.comparing(Employee::name, customKeyComparator)**: dùng một comparator riêng cho khóa, ví dụ muốn so không phân biệt hoa-thường hoặc xử lý null.

### 6.1. comparing() và khóa null

Nếu **name()** trả null và comparator khóa là natural order của String, sẽ có thể ném NullPointerException khi cần so sánh. Với khóa có thể null, nêu chính sách tường minh:

~~~java
Comparator<Employee> byNullableName =
        Comparator.comparing(
                Employee::name,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Ở đây **nullsLast** áp dụng cho **giá trị của khóa name**, không tự cho phép chính đối tượng Employee bị null. Nếu cả phần tử Employee có thể null, cần bọc comparator phần tử bằng **Comparator.nullsLast(...)** riêng.

## 7. Sắp xếp giảm dần bằng reversed và reverseOrder

Muốn đảo thứ tự tự nhiên của String:

~~~java
List<String> descending = List.of("Go", "Java", "C")
        .stream()
        .sorted(Comparator.reverseOrder())
        .toList();

System.out.println(descending); // [Java, Go, C]
~~~

**Comparator.reverseOrder()** tạo comparator đảo thứ tự tự nhiên. Khi có comparator riêng:

~~~java
Comparator<Integer> byValue = Integer::compare;
Comparator<Integer> reversed = byValue.reversed();
~~~

**reversed()** trả comparator có chiều so sánh đảo với comparator gốc; nó không thay đổi comparator gốc.

### 7.1. Cẩn thận vị trí reversed trong comparator nhiều khóa

Giả sử muốn **điểm cao trước**, khi bằng điểm thì **tên A-Z**:

~~~java
Comparator<Student> byScoreDescNameAsc =
        Comparator.comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
~~~

Đầu tiên đảo chiều **điểm**; sau đó thêm tiêu chí **tên tăng dần**. Nếu viết:

~~~java
Comparator<Student> different =
        Comparator.comparingInt(Student::score)
                .thenComparing(Student::name)
                .reversed();
~~~

thì **cả chuỗi tiêu chí** bị đảo: điểm giảm dần **và tên giảm dần**. Hai cách đều hợp lệ nhưng diễn đạt nghiệp vụ **khác nhau**. Vị trí gọi reversed rất quan trọng.

## 8. thenComparing: nhiều mức ưu tiên

Một số đối tượng có nhiều phần tử trùng khóa đầu tiên. Khi ấy, **thenComparing** giúp thêm tiêu chí phụ, chỉ được dùng khi tiêu chí trước xem hai phần tử bằng nhau.

~~~java
Comparator<Student> byScoreNameId =
        Comparator.comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name)
                .thenComparing(Student::id);
~~~

Thứ tự:

1. Điểm số cao nhất trước.
2. Nếu cùng điểm: tên tăng dần.
3. Nếu cùng điểm và tên: ID tăng dần.

**thenComparingInt** và các overload primitive khác cũng có thể dùng khi tiêu chí phụ là số:

~~~java
Comparator<Student> byNameThenScore =
        Comparator.comparing(Student::name)
                .thenComparingInt(Student::score);
~~~

Nếu muốn một tiêu chí phụ giảm dần, truyền comparator phụ riêng:

~~~java
Comparator<Student> byNameThenScoreDesc =
        Comparator.comparing(Student::name)
                .thenComparing(
                        Comparator.comparingInt(Student::score)
                                .reversed());
~~~

Các đoạn trong phần này cần một record/class Student phù hợp với score(), name(), id(). Chương trình đầy đủ ở phần 13 có định nghĩa ấy.

**Đặt tiêu chí ID ở cuối** là lựa chọn nghiệp vụ thường giúp tạo thứ tự xác định ngay cả khi những khóa trước trùng nhau. Nhưng nếu cố ý muốn giữ encounter order của các bản ghi cùng điểm và tên, có thể không thêm ID và dựa vào tính ổn định của sorted trên **ordered stream**.

## 9. Tính ổn định (stable) và encounter order

Theo hợp đồng của Java Stream, **sorted() trên ordered stream là stable**: nếu comparator trả 0 cho hai phần tử, thứ tự xuất hiện ban đầu của chúng vẫn được giữ trong kết quả.

Ví dụ nguồn:

~~~text
Student(id=S1, name=An, score=90)
Student(id=S2, name=Binh, score=95)
Student(id=S3, name=An, score=90)
~~~

Nếu comparator chỉ so **score giảm dần, rồi name tăng dần**, thì:

~~~text
S2 (Binh, 95)
S1 (An, 90)
S3 (An, 90)
~~~

S1 và S3 bằng nhau theo comparator (điểm 90 và tên An), nên trên List stream có thứ tự, S1 giữ vị trí tương đối trước S3.

**Với unordered stream, sorted không bảo đảm stable đối với các phần tử được comparator xem là bằng nhau.** Kết quả vẫn tuân thủ thứ tự so sánh, nhưng thứ tự tương đối của các phần tử trong cùng nhóm khóa có thể không được bảo đảm. Nếu nghiệp vụ cần thứ tự đồng nhất mọi lần, hãy tạo một **tiêu chí phụ rõ ràng** (ID, thời điểm tạo, thứ tự ưu tiên) thay vì dựa vào một encounter order không tồn tại.

### 9.1. Comparator trả 0 không nhất thiết bằng equals

Hai Student với cùng điểm và tên nhưng ID khác có thể **khác nhau theo equals**, dù comparator chỉ so điểm và tên trả 0. Đối với Stream.sorted, cả hai phần tử vẫn nằm trong kết quả, theo quy tắc sắp xếp.

Nhưng ở **TreeSet/TreeMap**, comparator xác định tính tương đương của khóa: compare(a,b)==0 có thể khiến một phần tử/khóa không được thêm như phần tử độc lập. Vì vậy, nếu cùng comparator được dùng cho cấu trúc tập/map có thứ tự, cần chú ý **tính nhất quán với equals** và yêu cầu nghiệp vụ đối với ID duy nhất.

## 10. Hợp đồng của Comparator phải nhất quán

Một Comparator đúng không chỉ “cho ra số” mà phải định nghĩa thứ tự nhất quán.

Những yêu cầu cốt lõi:

1. **Đối xứng về dấu:** sign(compare(a,b)) = -sign(compare(b,a)).
2. **Bắc cầu:** nếu a>b và b>c theo comparator, thì a>c.
3. **Nhất quán với quan hệ bằng theo comparator:** nếu compare(a,b)==0 thì kết quả so a và b với một z bất kỳ phải có cùng dấu.
4. Với một quá trình sort, các **khóa so sánh không được thay đổi bất ngờ**; comparator không nên phụ thuộc thời gian, random hoặc mutable shared state theo cách gây bất nhất.

Một Comparator trả kết quả tùy lượt gọi có thể dẫn đến thứ tự không xác định hoặc **IllegalArgumentException** từ thuật toán sort khi phát hiện vi phạm hợp đồng. Không được mong luôn có exception; nhiều comparator sai vẫn tình cờ “chạy xong” với dữ liệu nhỏ.

Ví dụ **không nên**:

~~~java
AtomicInteger counter = new AtomicInteger();
Comparator<Student> unstable = (a, b) ->
        counter.incrementAndGet() % 2 == 0 ? -1 : 1;
~~~

Đây là phản ví dụ dùng counter mutable để quyết định dấu. Kết quả không thể hiện một quan hệ thứ tự ổn định giữa a và b; nó thay đổi theo số lần comparator được gọi. **AtomicInteger** không cứu hợp đồng so sánh chỉ vì incrementAndGet là nguyên tử.

## 11. nullsFirst và nullsLast

Khi nguồn có thể chứa null, comparator tự nhiên thường không xử lý null. Có thể tạo chính sách:

~~~java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

List<String> values =
        Arrays.asList("Bee", null, "Ant", "Cat");

List<String> ordered = values.stream()
        .sorted(nullLast)
        .toList();

System.out.println(ordered);
// [Ant, Bee, Cat, null]
~~~

Mảnh ghép này cần import Comparator, List, Arrays. **List.of(...) không cho phép null**, nên ví dụ dùng Arrays.asList để tạo một danh sách có null.

- **nullsFirst(comparator)**: null được xếp trước giá trị khác null.
- **nullsLast(comparator)**: null được xếp sau giá trị khác null.

Nếu comparator truyền vào các wrapper này là null, mọi giá trị không null được xem tương đương theo thứ tự; không nên mặc định điều đó giải quyết nghiệp vụ chính xác. Nên cung cấp comparator cụ thể trừ khi thật sự muốn tất cả non-null ngang nhau.

**Quan trọng:** null element và null field là hai tình huống khác nhau. Muốn null field xếp cuối, dùng nullsLast ở comparator khóa; muốn null element xếp cuối, bọc comparator so sánh phần tử bằng nullsLast.

## 12. Thứ tự tác vụ trong Stream có ý nghĩa

### 12.1. sorted rồi limit

~~~java
List<Integer> smallestTwo =
        List.of(7, 1, 9, 3).stream()
                .sorted()
                .limit(2)
                .toList();
~~~

Kết quả **[1, 3]**: sắp cả nguồn theo thứ tự tăng dần rồi lấy hai phần tử đầu.

### 12.2. limit rồi sorted

~~~java
List<Integer> sortedPrefix =
        List.of(7, 1, 9, 3).stream()
                .limit(2)
                .sorted()
                .toList();
~~~

Kết quả **[1, 7]**: chỉ lấy hai phần tử đầu nguồn (7,1) rồi sắp chúng.

Do vậy không thể tùy tiện đổi **sorted().limit(k)** thành **limit(k).sorted()**. Một cách là lấy **top k tốt nhất toàn dữ liệu**; cách kia là sắp **k phần tử đầu**. Khác biệt này ảnh hưởng trực tiếp tới bài toán xếp hạng.

### 12.3. filter trước sorted

~~~java
List<Integer> chosen = numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();
~~~

Nếu yêu cầu là “chỉ lấy số dương rồi sắp”, lọc trước giúp giảm phần tử đi vào bước sort. Nhưng nếu điều kiện lọc phụ thuộc vị trí **sau khi sắp**, cần định nghĩa pipeline phù hợp; việc đổi thứ tự không luôn tương đương.

### 12.4. map trước sorted

~~~java
List<String> sortedNames = persons.stream()
        .map(Person::name)
        .sorted()
        .toList();
~~~

Đây là mảnh ghép với class Person và biến persons đã tồn tại. Nó sắp **String tên** và trả String, không sắp chính các đối tượng Person.

Nếu cần trả Person đã sắp theo tên, dùng:

~~~java
List<Person> sortedPersons = persons.stream()
        .sorted(Comparator.comparing(Person::name))
        .toList();
~~~

Phân biệt này quan trọng: **map làm đổi kiểu**, còn sorted chỉ thay đổi thứ tự của kiểu hiện tại.

## 13. Chương trình Java 17 chạy độc lập

Ví dụ dùng:

- **sorted()** cho String và int.
- **sorted(Comparator)** cho Student với điểm giảm dần, tên tăng dần.
- **Tính ổn định** khi hai Student trùng điểm và tên.
- **nullsLast** khi danh sách có null.
- **sorted().limit()** và **limit().sorted()**.
- **Stream.toList()** không sửa danh sách nguồn.

Tạo file **StreamSortingDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.IntStream;

public class StreamSortingDemo {
    record Student(String id, String name, int score) { }

    static String label(Student s) {
        return s.id() + ":" + s.name() + ":" + s.score();
    }

    public static void main(String[] args) {
        List<String> languages =
                List.of("Java", "Go", "Kotlin", "C", "java");

        System.out.println("natural: "
                + languages.stream().sorted().toList());

        List<Student> students = List.of(
                new Student("S1", "An", 90),
                new Student("S2", "Binh", 95),
                new Student("S3", "An", 90),
                new Student("S4", "Chi", 95)
        );

        Comparator<Student> byScoreDescNameAsc =
                Comparator.comparingInt(Student::score)
                        .reversed()
                        .thenComparing(Student::name);

        List<Student> ranked = students.stream()
                .sorted(byScoreDescNameAsc)
                .toList();

        System.out.println("ranked: "
                + ranked.stream()
                        .map(StreamSortingDemo::label)
                        .toList());

        System.out.println("original IDs: "
                + students.stream()
                        .map(Student::id)
                        .toList());

        List<String> withNull =
                Arrays.asList("Bee", null, "Ant", "Cat");

        System.out.println("null last: "
                + withNull.stream()
                        .sorted(Comparator.nullsLast(
                                Comparator.naturalOrder()))
                        .toList());

        int[] primitive = IntStream.of(7, 1, 9, 3)
                .sorted()
                .toArray();

        System.out.println("primitive: "
                + Arrays.toString(primitive));

        List<Integer> numbers = List.of(7, 1, 9, 3);

        System.out.println("sorted then limit: "
                + numbers.stream()
                        .sorted()
                        .limit(2)
                        .toList());

        System.out.println("limit then sorted: "
                + numbers.stream()
                        .limit(2)
                        .sorted()
                        .toList());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac StreamSortingDemo.java
java StreamSortingDemo
~~~

**Kết quả chính xác:**

~~~text
natural: [C, Go, Java, Kotlin, java]
ranked: [S2:Binh:95, S4:Chi:95, S1:An:90, S3:An:90]
original IDs: [S1, S2, S3, S4]
null last: [Ant, Bee, Cat, null]
primitive: [1, 3, 7, 9]
sorted then limit: [1, 3]
limit then sorted: [1, 7]
~~~

### 13.1. Phân tích thứ tự Student

Danh sách nguồn có S1, S2, S3, S4. Theo comparator:

1. **S2**: 95 điểm, tên Binh.
2. **S4**: 95 điểm, tên Chi; cùng điểm với S2 nên xét tên, Binh trước Chi.
3. **S1**: 90 điểm, tên An.
4. **S3**: 90 điểm, tên An; comparator đánh giá S1 và S3 bằng nhau, vì cả score và name trùng. Trên ordered Stream từ List, sorted **stable**, nên S1 đứng trước S3 theo encounter order.

Nếu bổ sung **thenComparing(Student::id)** thì comparator sẽ có tiêu chí thứ ba; khi đó thứ tự nhóm bằng điểm/tên được quyết định bởi ID thay vì nhờ tính ổn định.

### 13.2. Nguồn không thay đổi

Dòng **original IDs** vẫn là **[S1, S2, S3, S4]**. Việc gọi **students.stream().sorted(...)** không sắp lại List.of nguồn. Danh sách kết quả của Stream.toList cũng không hỗ trợ mutation, nên không thể gọi add/set/remove trực tiếp trên nó.

Các record Student chứa String và int, giúp dữ liệu ổn định trong ví dụ. Với đối tượng mutable trong ứng dụng thật, danh sách kết quả **không được deep-copy**; cập nhật field của một Student có thể được quan sát qua cả nguồn và kết quả vì chúng tham chiếu cùng object.

### 13.3. Primitive sorted

**IntStream.sorted()** luôn sắp int theo thứ tự tăng dần. Nếu muốn số lớn trước trong một Stream<Integer> có Comparator, có thể dùng:

~~~java
List<Integer> descending = IntStream.of(7, 1, 9, 3)
        .boxed()
        .sorted(Comparator.reverseOrder())
        .toList();
~~~

Kết quả **[9, 7, 3, 1]**. Lệnh **boxed()** chuyển primitive int thành Integer để tạo Stream<Integer>; từ đó mới dùng overload **sorted(Comparator)** của reference Stream. Điều này có thể phát sinh boxing, nên chỉ nên làm khi thực sự cần quy tắc comparator hoặc kiểu đối tượng.

## 14. sorted là lazy nhưng stateful

Ví dụ:

~~~java
Stream<Integer> pipeline = Stream.of(9, 2, 5)
        .sorted();

// Chưa có terminal operation ở đây.

int minimum = pipeline.findFirst().orElseThrow();
System.out.println(minimum); // 2
~~~

Gọi sorted() không tự sắp ngay khi tạo pipeline. Khi **findFirst()** yêu cầu phần tử đầu sau sort, sắp xếp tổng quát thường phải biết toàn bộ các phần tử đến giai đoạn sorted để xác định phần tử nhỏ nhất. Vì vậy **findFirst không bảo đảm chỉ đọc một phần tử của nguồn** khi đứng sau sorted.

Điều này phân biệt sorted với một thao tác trung gian **stateless** như map/filter. Trong nhiều pipeline sequential, map/filter có thể được ghép xử lý từng phần tử mà không đệm toàn bộ kết quả; sorted lại là **stateful** và có chi phí bộ nhớ/CPU cho việc so sánh.

**Lưu ý:** Stream có thể tối ưu trong một số trường hợp, và một số nguồn đã được đánh dấu SORTED sẵn; không nên lấy mô hình “luôn cấp đúng một array kích thước N” làm hợp đồng JDK. Hãy hiểu rủi ro chi phí và sự phụ thuộc của kết quả vào thứ tự, thay vì phụ thuộc nội bộ của implementation.

### 14.1. Cân nhắc dữ liệu lớn và Stream vô hạn

Một pipeline cố sắp **toàn bộ một nguồn vô hạn** sẽ không thể hoàn tất theo cách sắp xếp tổng quát cần xem tất cả giá trị trước khi phát phần tử đầu. Ví dụ:

~~~java
// Tránh nếu không có bước giới hạn thích hợp:
// Stream.iterate(1, n -> n + 1).sorted().findFirst();
~~~

Nếu nghiệp vụ thật sự chỉ cần **k phần tử có giá trị tốt nhất trong dữ liệu hữu hạn**, cân nhắc thuật toán top-k dựa trên priority queue hoặc API tối ưu riêng khi N rất lớn, thay vì luôn sort toàn bộ. Đối với dữ liệu thông thường, sorted().limit(k) vẫn là cách diễn đạt rõ ràng và an toàn khi tính đúng đắn quan trọng hơn tối ưu sớm.

### 14.2. sorted và count không đồng nghĩa comparator được gọi

Một trường hợp dễ hiểu sai:

~~~java
long count = List.of(3, 1, 2).stream()
        .sorted()
        .count();
~~~

**Kết quả là 3**, và với nguồn có kích thước biết trước, terminal count có thể tối ưu dựa trên số phần tử mà không thực sự thực hiện việc sort. Vì vậy không được đặt side effect nghiệp vụ bắt buộc trong Comparator, map hoặc peek rồi kỳ vọng sorted().count() sẽ chạy mọi callback.

## 15. sorted so với List.sort và Collections.sort

| API | Có sửa nguồn? | Kết quả |
| --- | --- | --- |
| **source.stream().sorted(...).toList()** | Không, nếu callback không can thiệp | List kết quả mới về mặt tập hợp, unmodifiable theo Stream.toList |
| **source.sort(comparator)** | Có, trên List hỗ trợ sửa | void; chính List bị sắp lại |
| **Collections.sort(list)** | Có, trên List hỗ trợ sửa | void; sort theo natural order |
| **Collections.sort(list, comparator)** | Có, trên List hỗ trợ sửa | void; sort theo Comparator |
| **Arrays.sort(array)** | Có, trên array | Thay thứ tự phần tử trong mảng |

Ví dụ:

~~~java
List<Integer> original = new ArrayList<>(List.of(3, 1, 2));

List<Integer> snapshotSorted = original.stream()
        .sorted()
        .toList();

System.out.println(original);     // [3, 1, 2]
System.out.println(snapshotSorted); // [1, 2, 3]

original.sort(Comparator.naturalOrder());
System.out.println(original);     // [1, 2, 3]
~~~

**List.of** là unmodifiable, nên không nên gọi **sort** trực tiếp trên List.of khi cần sửa thứ tự; dùng bản sao mutable **new ArrayList<>(...)** trước.

**Stream.toList() không bảo đảm một deep copy**: nếu phần tử là object mutable, cả list nguồn và list kết quả có thể giữ cùng tham chiếu object.

## 16. Quan sát khi debug với peek và side effect

Bối cảnh của sorted thường đi cùng nhu cầu quan sát pipeline:

~~~java
List<Integer> values = List.of(4, 1, 3, 2)
        .stream()
        .peek(n -> System.out.println("before: " + n))
        .sorted()
        .peek(n -> System.out.println("after: " + n))
        .toList();
~~~

Đây là mảnh ghép trong phương thức có import List. Nó minh họa vị trí **trước/ sau sorted** và có thể hữu ích khi học hoặc debug. Nhưng **peek** là intermediate operation; callback của peek **không được bảo đảm chạy đầy đủ** trong mọi pipeline, vì terminal hoặc tối ưu có thể bỏ qua những phần không cần thiết.

**Không đưa chức năng bắt buộc** như ghi nhận thanh toán, gửi email hoặc audit vào Comparator/peek. Comparator có thể được gọi nhiều lần và với thứ tự không cố định; một phép sort có thể cần gọi compare(a,b) nhiều lần với cùng cặp. Nếu side effect làm thay đổi khóa so sánh, comparator còn có thể vi phạm hợp đồng.

Khi cần ghi log nghiệp vụ, hãy tách bước tính kết quả và bước xử lý sự kiện thành những phần có hợp đồng lỗi/transaction rõ ràng.

## 17. sorted trong parallel stream

**sorted** vẫn có semantics sắp xếp khi dùng trên parallel stream, nhưng việc thực thi có thể chia nguồn, xử lý các nhánh và hợp nhất kết quả. Chú ý:

- **Comparator phải stateless và thread-safe theo cách nó được dùng**. Một Comparator chỉ đọc các field bất biến thường phù hợp hơn Comparator dùng biến mutable chia sẻ.
- **Ordered stream** vẫn có hợp đồng stable của sorted; **unordered stream** không có bảo đảm stable tương ứng.
- Chi phí buffer, hợp nhất và đồng bộ có thể cao; parallel không phải lúc nào cũng nhanh hơn.
- **peek/forEach** khi parallel có thể quan sát callback chạy ở nhiều thread hoặc không theo thứ tự encounter; đừng dùng thứ tự log để suy luận thứ tự kết quả sắp xếp.
- Nếu dữ liệu quá nhỏ hoặc comparator nhẹ, overhead của parallel có thể làm chậm hơn sequential.

Ví dụ:

~~~java
List<Student> result = students.parallelStream()
        .sorted(byScoreDescNameAsc)
        .toList();
~~~

Đây là mảnh ghép với dữ liệu và comparator đã khai báo trong phần 13. Thứ tự **kết quả** tuân thủ comparator; không suy luận rằng các lời gọi Comparator xảy ra theo thứ tự S1→S2→S3→S4.

## 18. Kiểm thử Comparator và thứ tự kết quả

Đối với một comparator nghiệp vụ, cần kiểm thử **dấu**, **trường hợp bằng nhau**, **tính bắc cầu** và **thứ tự của kết quả sort**.

### 18.1. Test dấu so sánh

~~~java
Comparator<Integer> ascending = Integer::compare;
if (ascending.compare(1, 2) >= 0) {
    throw new AssertionError("Expected 1 before 2");
}
if (ascending.compare(2, 2) != 0) {
    throw new AssertionError("Expected equality by comparator");
}
if (ascending.compare(3, 2) <= 0) {
    throw new AssertionError("Expected 3 after 2");
}
~~~

Đây là đoạn test minh họa trong phương thức đã import Comparator.

### 18.2. Test nhiều tiêu chí và sự ổn định

Với Student từ chương trình phần 13, hãy kiểm tra:

- S2 đứng trước S4 vì cùng 95 điểm nhưng Binh đứng trước Chi.
- S1 đứng trước S3 khi cả hai cùng 90 điểm và tên An, vì nguồn là ordered List.
- Nếu thêm khóa ID giảm dần, thứ tự S1/S3 có thể đổi theo chính sách ID; hãy cập nhật test để mô tả rõ mong muốn.
- Sắp xếp không làm đổi thứ tự của list nguồn.

### 18.3. Test null và giá trị biên

Hãy thử:

- Null element theo nullsFirst/nullsLast.
- Null field name khi comparator lấy khóa.
- Integer.MIN_VALUE và Integer.MAX_VALUE nếu comparator làm việc với số.
- Các giá trị bằng nhau, dữ liệu đã được sắp, dữ liệu hoàn toàn đảo thứ tự và collection rỗng.
- Số thực NaN nếu nghiệp vụ có thể gặp.
- Comparator dùng trạng thái mutable: thay bằng comparator thuần/ổn định trước khi đưa vào production.

Chỉ vì 5 phần tử sắp đúng **chưa chứng minh** một comparator luôn bắc cầu. Với dữ liệu quan trọng, test ngẫu nhiên/property-based testing có thể giúp kiểm tra tính đối xứng dấu và bắc cầu trên nhiều bộ ba giá trị.

## 19. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Gọi sorted() cho đối tượng không Comparable | Không có natural order | Truyền Comparator hoặc thiết kế Comparable phù hợp |
| Cho rằng sorted() sửa List nguồn | Stream chỉ tạo pipeline kết quả | Dùng List.sort riêng khi muốn mutation |
| Dùng (a,b) -> a-b | Phép trừ có thể overflow | Integer.compare hoặc comparingInt |
| Gọi reversed() ở cuối cả chain mà chỉ muốn đảo điểm | Đảo toàn bộ comparator | Đảo comparator điểm trước thenComparing |
| Comparator đổi kết quả theo lượt gọi | Vi phạm hợp đồng thứ tự | Dùng quy tắc thuần và khóa ổn định |
| Quên null key/element | Có thể ném NPE | nullsFirst/nullsLast ở đúng tầng |
| Hiểu compare(a,b)==0 là a.equals(b) | Tương đương theo comparator khác equals | Thêm tiêu chí phụ nếu cần phân biệt |
| Giả định sorted luôn stable với nguồn unordered | Không có bảo đảm stable trong trường hợp này | Thêm tiêu chí phụ rõ ràng |
| Đưa sorted sau limit khi cần top-k toàn bộ | Chỉ sắp prefix | sorted rồi limit hoặc thuật toán top-k đúng |
| Cho rằng sorted.findFirst chỉ đọc một phần tử | Sorted có thể cần toàn bộ dữ liệu | Xem cả pipeline |
| Gọi sorted trên nguồn vô hạn | Không hoàn tất khi cần sắp tổng quát toàn bộ | Giới hạn nguồn trước hoặc thiết kế thuật toán khác |
| Dùng peek/comparator để audit | Không có bảo đảm số lần gọi hoặc thứ tự | Tách bước audit khỏi pipeline sort |
| Gọi List.sort trên List.of | List không hỗ trợ mutation | Dùng ArrayList mới hoặc Stream.sorted |
| Dùng Comparator cho IntStream.sorted() | Primitive stream không có overload comparator | boxed() rồi sorted(comparator) nếu cần |

## 20. Bài tập tự luyện

### Bài 1 — Natural order

Cho **List.of("java", "Go", "C", "Java")**. Hãy dự đoán kết quả sau **stream().sorted().toList()**.

**Gợi ý đáp án:** **[C, Go, Java, java]** vì String natural order phân biệt chữ hoa/thường.

### Bài 2 — So điểm giảm dần, tên tăng dần

Viết comparator cho record:

~~~java
record Candidate(String name, int score) { }
~~~

Yêu cầu điểm cao trước, khi bằng điểm thì tên A-Z.

**Gợi ý:**

~~~java
Comparator<Candidate> ranking =
        Comparator.comparingInt(Candidate::score)
                .reversed()
                .thenComparing(Candidate::name);
~~~

Các đoạn này minh họa trong lớp có import Comparator và record Candidate.

### Bài 3 — So sánh vị trí limit

Với nguồn **[8, 2, 9, 1]**, hãy tính:

~~~java
numbers.stream().sorted().limit(2).toList();
numbers.stream().limit(2).sorted().toList();
~~~

**Đáp án:** **[1, 2]** và **[2, 8]**. Câu đầu chọn hai số nhỏ nhất toàn bộ; câu sau chỉ sắp hai phần tử đầu nguồn.

### Bài 4 — Xử lý null

Cho **["B", null, "A"]**. Viết pipeline để sắp **A, B, null**.

**Đáp án gợi ý:**

~~~java
List<String> result = values.stream()
        .sorted(Comparator.nullsLast(
                Comparator.naturalOrder()))
        .toList();
~~~

**values** phải là một danh sách cho phép phần tử null, chẳng hạn tạo bằng Arrays.asList.

### Bài 5 — Sửa comparator không an toàn

~~~java
Comparator<Integer> wrong = (a, b) -> a - b;
~~~

Hãy sửa và kiểm thử với **Integer.MAX_VALUE** và **-1**.

**Đáp án:** dùng **Integer::compare**, vì tính thứ tự đúng không thể phụ thuộc phép trừ có nguy cơ tràn.

### Bài 6 — Thứ tự ổn định và ID

Có hai Student cùng score=90, cùng name=An nhưng ID S3/S1 xuất hiện theo thứ tự khác nhau. Khi nào kết quả cần giữ encounter order và khi nào cần sắp theo ID?

**Gợi ý:** nếu yêu cầu **ổn định theo thứ tự gốc**, dùng comparator không có ID trên ordered source; nếu yêu cầu **thứ tự xác định độc lập nguồn**, thêm **thenComparing(Student::id)**.

## 21. Ghi nhớ

**Stream.sorted()** dùng **thứ tự tự nhiên**; **Stream.sorted(Comparator)** dùng **quy tắc do bạn định nghĩa**. Trong cả hai trường hợp, sorted là **intermediate operation lazy nhưng stateful**, không trực tiếp thay đổi List nguồn và chỉ được đánh giá khi terminal yêu cầu.

Hãy ghi nhớ các nguyên tắc:

- Dùng **Comparable** khi kiểu có natural order rõ ràng; dùng **Comparator** cho các chính sách sắp xếp khác nhau.
- Ưu tiên **Comparator.comparing/comparingInt**, **thenComparing**, **reversed**, **nullsFirst/nullsLast** để thể hiện tiêu chí minh bạch.
- Comparator phải nhất quán, bắc cầu, không phụ thuộc trạng thái thay đổi; **tránh phép trừ có thể overflow**.
- Với **ordered stream**, sorted stable khi comparator xem hai phần tử bằng nhau; với unordered stream, không có bảo đảm ổn định tương ứng.
- **sorted().limit(k)** khác **limit(k).sorted()** về kết quả; không đổi thứ tự một cách tùy tiện.
- **Stream.toList()** cho kết quả unmodifiable, nhưng không sao chép sâu các đối tượng phần tử.
- Nếu thật sự muốn sửa collection gốc, dùng **List.sort** trên danh sách mutable; nếu chỉ muốn tạo kết quả sắp xếp, dùng **Stream.sorted**.

Đọc đúng thứ tự tự nhiên, hợp đồng comparator và vị trí sorted trong pipeline sẽ giúp bạn vừa có kết quả đúng, vừa tránh những lỗi ngầm khó phát hiện khi dữ liệu lớn hoặc yêu cầu nghiệp vụ thay đổi.
