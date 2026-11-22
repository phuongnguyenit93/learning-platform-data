# Comparator cho mảng đối tượng trong Java

## 1. Comparator dùng để làm gì?

Comparator định nghĩa thứ tự tùy chỉnh giữa hai đối tượng. Khi cần sắp xếp mảng đối tượng theo một thuộc tính, nhiều thuộc tính hoặc một quy tắc nghiệp vụ, có thể truyền Comparator vào các phương thức của lớp Arrays.

Phương thức so sánh có dạng:

~~~java
int compare(T left, T right)
~~~

Kết quả có ý nghĩa:

- Số âm: left đứng trước right.
- Số dương: left đứng sau right.
- Số 0: hai đối tượng tương đương theo thứ tự do Comparator định nghĩa.

Comparator không thay đổi đối tượng và cũng không loại bỏ phần tử trùng. Nó chỉ xác định thứ tự khi sắp xếp hoặc quan hệ thứ tự mà một số cấu trúc dữ liệu có thứ tự sử dụng.

Trong Java hiện đại, nên ưu tiên các factory và phương thức kết hợp của Comparator như comparing, comparingInt, thenComparing, reversed, nullsFirst và nullsLast. Chúng giúp biểu diễn quy tắc sắp xếp rõ ràng, tránh lỗi so sánh thủ công.

## 2. Sắp xếp mảng đối tượng bằng Arrays.sort

Với mảng đối tượng, có thể truyền Comparator vào overload Arrays.sort:

~~~java
Arrays.sort(array, comparator);
~~~

Ví dụ sắp xếp chuỗi theo độ dài:

~~~java
String[] names = {"Minh", "An", "Binh", "Lan"};

Arrays.sort(names, Comparator.comparingInt(String::length));

System.out.println(Arrays.toString(names));
~~~

Kết quả:

~~~text
[An, Lan, Minh, Binh]
~~~

Các chuỗi có cùng độ dài giữ nguyên thứ tự tương đối ban đầu vì overload sort cho mảng đối tượng có tính ổn định. Tính ổn định có nghĩa là nếu Comparator trả về 0 cho hai phần tử, thứ tự trước đó của chúng được giữ nguyên trong kết quả.

Không phải mọi overload của Arrays.sort đều nhận Comparator. Các overload cho mảng nguyên thủy như int[], long[] hoặc double[] sử dụng thứ tự tự nhiên của kiểu số và không nhận Comparator. Nếu cần quy tắc tùy chỉnh cho dữ liệu số, hãy dùng mảng đối tượng như Integer[] hoặc tạo kiểu đối tượng phù hợp.

## 3. Tạo Comparator bằng comparing và comparingInt

Comparator.comparing nhận một hàm trích xuất khóa. Kiểu khóa phải có thứ tự tự nhiên hoặc cần truyền thêm Comparator để so sánh khóa:

~~~java
Comparator<Person> byName =
    Comparator.comparing(Person::name);
~~~

Khi khóa là int, long hoặc double, nên dùng các biến thể chuyên biệt:

~~~java
Comparator<Person> byAge =
    Comparator.comparingInt(Person::age);

Comparator<Person> bySalary =
    Comparator.comparingLong(Person::salary);

Comparator<Person> byScore =
    Comparator.comparingDouble(Person::score);
~~~

Các phương thức chuyên biệt tránh việc đóng gói giá trị nguyên thủy thành wrapper chỉ để so sánh. Chúng cũng thể hiện rõ kiểu khóa mà quy tắc sắp xếp đang dùng.

Không nên tự viết phép trừ để tạo Comparator:

~~~java
// Không nên dùng: có thể tràn số nguyên.
(a, b) -> a.age() - b.age()
~~~

Hãy dùng comparingInt hoặc Integer.compare:

~~~java
Comparator<Person> byAge =
    Comparator.comparingInt(Person::age);

// Cách viết thủ công tương đương về mục đích:
Comparator<Person> byAgeManual =
    (a, b) -> Integer.compare(a.age(), b.age());
~~~

Nếu khóa là một lớp không triển khai Comparable, hãy truyền Comparator cho overload comparing:

~~~java
Comparator<Person> byNameIgnoreCase =
    Comparator.comparing(
        Person::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

## 4. Sắp xếp theo nhiều tiêu chí với thenComparing

thenComparing bổ sung tiêu chí khi tiêu chí trước trả về 0. Ví dụ, sắp xếp nhân viên theo tuổi tăng dần, sau đó theo tên:

~~~java
Comparator<Person> byAgeThenName = Comparator
    .comparingInt(Person::age)
    .thenComparing(Person::name);
~~~

Quy tắc được áp dụng theo thứ tự:

1. So sánh tuổi.
2. Nếu tuổi bằng nhau, so sánh tên.
3. Nếu cả tuổi và tên đều bằng nhau theo các Comparator tương ứng, kết quả là 0.

Có thể thêm nhiều tiêu chí:

~~~java
Comparator<Employee> order = Comparator
    .comparing(Employee::department)
    .thenComparingInt(Employee::level)
    .thenComparing(Employee::name);
~~~

Thứ tự ưu tiên là phòng ban, cấp bậc, rồi tên. Chỉ khi hai đối tượng bằng nhau theo tiêu chí trước mới xét tiêu chí tiếp theo.

Nếu cần sắp xếp tên không phân biệt hoa thường:

~~~java
Comparator<Person> byAgeThenName = Comparator
    .comparingInt(Person::age)
    .thenComparing(
        Person::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

Nếu Comparator kết thúc bằng 0 cho hai đối tượng có dữ liệu khác nhau, sort vẫn giữ cả hai đối tượng. Khi cần thứ tự xác định hoàn toàn, hãy thêm tiêu chí phân biệt phù hợp, chẳng hạn mã định danh duy nhất.

## 5. Đảo thứ tự với reversed

reversed() tạo Comparator có thứ tự đảo ngược so với Comparator hiện tại:

~~~java
Comparator<Person> byAgeAscending =
    Comparator.comparingInt(Person::age);

Comparator<Person> byAgeDescending =
    byAgeAscending.reversed();
~~~

Có một điểm dễ nhầm khi kết hợp với thenComparing. reversed() đảo toàn bộ Comparator đã xây dựng đến vị trí gọi nó:

~~~java
Comparator<Person> reverseAgeAndName = Comparator
    .comparingInt(Person::age)
    .thenComparing(Person::name)
    .reversed();
~~~

Comparator trên sắp xếp tuổi giảm dần và tên giảm dần trong nhóm tuổi bằng nhau.

Nếu yêu cầu là tuổi giảm dần nhưng tên vẫn tăng dần, hãy đảo tiêu chí tuổi trước khi thêm tiêu chí tên:

~~~java
Comparator<Person> ageDescendingNameAscending = Comparator
    .comparingInt(Person::age)
    .reversed()
    .thenComparing(Person::name);
~~~

Comparator này thường đúng với yêu cầu nghiệp vụ kiểu “mới nhất trước, tên theo alphabet”. Vị trí gọi reversed() quyết định tiêu chí nào bị đảo.

Các factory tiện ích cũng có sẵn:

~~~java
Comparator<Integer> ascending = Comparator.naturalOrder();
Comparator<Integer> descending = Comparator.reverseOrder();
~~~

naturalOrder và reverseOrder phù hợp khi kiểu phần tử đã triển khai Comparable.

## 6. Xử lý phần tử null và thuộc tính null

Mặc định, nhiều Comparator tạo bởi comparing không chấp nhận khóa null. Nếu mảng có thể chứa null, hãy xác định chính sách rõ ràng bằng nullsFirst hoặc nullsLast:

~~~java
Comparator<Person> byAge = Comparator
    .comparingInt(Person::age);

Comparator<Person> nullLast = Comparator.nullsLast(byAge);
Comparator<Person> nullFirst = Comparator.nullsFirst(byAge);
~~~

Khi truyền nullLast vào Arrays.sort, phần tử null được đặt ở cuối. nullFirst đặt chúng ở đầu.

Cần phân biệt hai tình huống:

- Phần tử trong mảng là null.
- Đối tượng không null nhưng thuộc tính dùng làm khóa là null.

Để xử lý phần tử mảng null, bọc Comparator của đối tượng bằng nullsFirst hoặc nullsLast:

~~~java
Arrays.sort(people, Comparator.nullsLast(byAge));
~~~

Để xử lý thuộc tính tên có thể null, truyền Comparator xử lý null cho khóa:

~~~java
Comparator<Person> byNameNullLast = Comparator.comparing(
    Person::name,
    Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
);
~~~

Nếu cả phần tử Person và thuộc tính name đều có thể null, cần kết hợp hai lớp chính sách:

~~~java
Comparator<Person> byNameNullLast = Comparator.nullsLast(
    Comparator.comparing(
        Person::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    )
);
~~~

Không nên dùng nullsLast để che giấu dữ liệu null khi null thực sự là dữ liệu không hợp lệ. Hãy chọn một trong hai cách: từ chối dữ liệu ở ranh giới đầu vào hoặc quy định vị trí của null trong thứ tự sắp xếp.

## 7. Arrays.parallelSort và khi nào nên dùng

Arrays.parallelSort có overload nhận Comparator cho mảng đối tượng:

~~~java
Arrays.parallelSort(people, byAgeThenName);
~~~

Phương thức này có từ Java 8 và chia công việc sắp xếp thành các tác vụ có thể thực hiện song song. Nó phù hợp để cân nhắc với mảng lớn trên môi trường có nhiều lõi xử lý.

Với mảng nhỏ, chi phí chia tác vụ và phối hợp có thể lớn hơn lợi ích. Không nên mặc định parallelSort luôn nhanh hơn sort. Hãy đo bằng dữ liệu đại diện nếu hiệu năng là yêu cầu quan trọng.

Comparator được dùng trong sắp xếp song song phải an toàn khi được gọi đồng thời. Tránh Comparator có trạng thái thay đổi dùng chung, phụ thuộc vào thứ tự gọi hoặc tạo tác dụng phụ. Comparator thuần, chỉ đọc các thuộc tính của hai đối tượng, thường là lựa chọn tốt.

## 8. Tìm kiếm nhị phân sau khi sắp xếp

Arrays.binarySearch có overload nhận Comparator:

~~~java
Arrays.binarySearch(array, key, comparator);
~~~

Mảng phải được sắp xếp trước theo cùng quy tắc Comparator. Nếu dùng Comparator khác hoặc mảng chưa được sắp xếp theo Comparator đó, kết quả không được bảo đảm.

Ví dụ:

~~~java
Comparator<Person> byAgeThenName = Comparator
    .comparingInt(Person::age)
    .thenComparing(Person::name);

Arrays.sort(people, byAgeThenName);

int index = Arrays.binarySearch(
    people,
    new Person("Binh", 25),
    byAgeThenName
);
~~~

Nếu tìm thấy phần tử tương đương theo Comparator, phương thức trả về một chỉ số không âm. Nếu không tìm thấy, kết quả âm được tính theo công thức -(insertion point) - 1. Insertion point là vị trí mà khóa có thể được chèn để vẫn giữ thứ tự.

Khi có nhiều phần tử so sánh bằng nhau, binarySearch không cam kết trả về phần tử đầu tiên hoặc cuối cùng trong nhóm. Nếu cần tìm toàn bộ nhóm, hãy xác định biên trái và biên phải bằng tìm kiếm riêng hoặc dùng cấu trúc dữ liệu phù hợp.

## 9. Hợp đồng của Comparator

Comparator cần tuân thủ các quy tắc nhất quán để thuật toán sắp xếp hoạt động đúng:

- Đổi chỗ hai đối số phải đảo dấu kết quả so sánh.
- Nếu a đứng trước b và b đứng trước c thì a phải đứng trước c.
- Nếu a và b so sánh bằng nhau, chúng phải có quan hệ so sánh nhất quán với các phần tử khác.
- Kết quả không nên thay đổi tùy tiện giữa các lần gọi với cùng dữ liệu.

Comparator có thể không nhất quán với equals. Điều đó vẫn có thể dùng cho sắp xếp mảng, nhưng cần hiểu hệ quả: hai đối tượng khác nhau theo equals vẫn có thể nhận kết quả compare bằng 0. Arrays.sort vẫn giữ cả hai; TreeSet hoặc TreeMap có thể xem chúng là cùng một phần tử hoặc khóa theo Comparator.

Ví dụ Comparator theo độ tuổi:

~~~java
Comparator<Person> byAgeOnly =
    Comparator.comparingInt(Person::age);
~~~

Hai người khác tên nhưng cùng tuổi sẽ so sánh bằng nhau theo Comparator này. Nếu chỉ sắp xếp và muốn giữ thứ tự ban đầu trong nhóm tuổi bằng nhau, đây là hành vi hợp lệ nhờ sort ổn định. Nếu cần phân biệt họ, thêm thenComparing(Person::name).

Tránh Comparator phụ thuộc vào thuộc tính thay đổi trong lúc sắp xếp. Nếu tuổi hoặc khóa sắp xếp thay đổi giữa các lần so sánh, quan hệ thứ tự có thể mất tính nhất quán và gây kết quả sai hoặc IllegalArgumentException trong một số trường hợp.

## 10. Ví dụ chạy được

Chương trình sau minh họa sắp xếp mảng đối tượng theo nhiều tiêu chí, đảo một tiêu chí, xử lý phần tử null, tìm kiếm nhị phân và tính ổn định của sort.

**Tệp ComparatorArrayDemo.java:**

~~~java
import java.util.Arrays;
import java.util.Comparator;

public class ComparatorArrayDemo {
    record Person(String name, int age) { }

    private static String describe(Person person) {
        return person.name() + ":" + person.age();
    }

    public static void main(String[] args) {
        Person[] people = {
            new Person("Lan", 30),
            new Person("Binh", 25),
            new Person("An", 25),
            new Person("Minh", 35)
        };

        Comparator<Person> byAgeThenName = Comparator
                .comparingInt(Person::age)
                .thenComparing(Person::name);

        Arrays.sort(people, byAgeThenName);
        System.out.println("ascending: " + Arrays.toString(
                Arrays.stream(people)
                    .map(ComparatorArrayDemo::describe)
                    .toArray()));

        Person[] descending = people.clone();
        Arrays.sort(descending,
                Comparator.comparingInt(Person::age).reversed()
                        .thenComparing(Person::name));
        System.out.println("age descending: " + Arrays.toString(
                Arrays.stream(descending)
                    .map(ComparatorArrayDemo::describe)
                    .toArray()));

        Person[] nullable = {
            new Person("An", 25), null, new Person("Binh", 25)
        };
        Arrays.sort(nullable, Comparator.nullsLast(byAgeThenName));
        System.out.println("null last: " + Arrays.toString(
                Arrays.stream(nullable)
                    .map(p -> p == null ? "null" : describe(p))
                    .toArray()));

        int index = Arrays.binarySearch(
            people,
            new Person("Binh", 25),
            byAgeThenName
        );
        System.out.println("binary search Binh: " + index);

        Person[] stable = {
            new Person("Binh", 25),
            new Person("An", 25),
            new Person("Lan", 30)
        };
        Arrays.sort(stable, Comparator.comparingInt(Person::age));
        System.out.println("stable age-only: " + Arrays.toString(
                Arrays.stream(stable)
                    .map(ComparatorArrayDemo::describe)
                    .toArray()));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all ComparatorArrayDemo.java
java ComparatorArrayDemo
~~~

Kết quả chuẩn:

~~~text
ascending: [An:25, Binh:25, Lan:30, Minh:35]
age descending: [Minh:35, Lan:30, An:25, Binh:25]
null last: [An:25, Binh:25, null]
binary search Binh: 1
stable age-only: [Binh:25, An:25, Lan:30]
~~~

Ví dụ dùng record để giữ dữ liệu Person gọn. Record có từ Java 16; nếu dự án chạy Java 8 hoặc Java 11, có thể thay record bằng một class thông thường có constructor và accessor tương ứng. Các API Comparator và Arrays.sort dùng trong ví dụ đã có từ các phiên bản Java trước đó.

## 11. Lỗi thường gặp và cách khắc phục

- **Dùng phép trừ trong Comparator:** có thể tràn số. Dùng comparingInt hoặc Integer.compare.
- **Quên tiêu chí phụ:** các đối tượng có cùng khóa chính có thể giữ thứ tự đầu vào. Thêm thenComparing nếu cần thứ tự xác định hơn.
- **Gọi reversed() sai vị trí:** reversed() đảo toàn bộ Comparator đứng trước nó. Đảo riêng từng tiêu chí tại đúng vị trí.
- **Không xử lý null:** so sánh phần tử hoặc khóa null có thể ném NullPointerException. Dùng nullsFirst/nullsLast hoặc xác thực dữ liệu trước.
- **Dùng binarySearch trên mảng chưa sắp xếp:** phải sort bằng cùng Comparator trước khi tìm.
- **Cho rằng Comparator loại bỏ phần tử trùng:** sort chỉ sắp xếp, không loại phần tử. Dùng Set hoặc xử lý riêng nếu muốn loại trùng.
- **Dùng Comparator có tác dụng phụ hoặc trạng thái thay đổi:** có thể phá vỡ hợp đồng so sánh. Ưu tiên Comparator không trạng thái và nhất quán.
- **Nhầm compare bằng 0 với equals:** compare bằng 0 chỉ nói hai phần tử tương đương theo thứ tự Comparator. Nó không tự khẳng định equals trả về true.

## 12. Chọn API theo nhu cầu

| Nhu cầu | API |
|---|---|
| Sắp xếp mảng đối tượng theo quy tắc tùy chỉnh | Arrays.sort(array, comparator) |
| Sắp xếp mảng đối tượng song song | Arrays.parallelSort(array, comparator) |
| Lấy khóa số nguyên để so sánh | Comparator.comparingInt |
| Sắp xếp theo nhiều tiêu chí | thenComparing |
| Đảo toàn bộ thứ tự hiện tại | reversed |
| Đưa null lên đầu hoặc xuống cuối | nullsFirst, nullsLast |
| Tìm phần tử trong mảng đã sắp xếp | Arrays.binarySearch(array, key, comparator) |
| Sắp xếp theo thứ tự tự nhiên | Comparator.naturalOrder |
| Sắp xếp theo thứ tự tự nhiên đảo ngược | Comparator.reverseOrder |

## 13. Ghi nhớ

Comparator mô tả thứ tự giữa hai đối tượng. Dùng Arrays.sort(array, comparator) để sắp xếp mảng đối tượng, comparing hoặc comparingInt để chọn khóa, thenComparing để thêm tiêu chí và reversed để đảo thứ tự. Dùng nullsFirst/nullsLast khi null là trường hợp hợp lệ. Khi tìm bằng binarySearch, mảng phải được sắp xếp bằng cùng Comparator. Giữ Comparator nhất quán, không dùng phép trừ có nguy cơ tràn và nhớ rằng compare bằng 0 không có nghĩa là sort loại bỏ một phần tử.
