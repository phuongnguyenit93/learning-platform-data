# Thứ tự tự nhiên: compareTo() trả về dấu âm, bằng không hoặc dấu dương

## 1. Ý nghĩa chính xác của kết quả compareTo

Trong Java, một lớp triển khai **Comparable<T>** khi muốn xác định thứ tự tự nhiên (natural ordering) cho các đối tượng cùng kiểu. Phương thức compareTo(T other) trả về một giá trị kiểu int, nhưng **dấu** của kết quả mới biểu thị quan hệ:

| Giá trị x.compareTo(y) | Ý nghĩa | Sắp xếp tăng dần |
| --- | --- | --- |
| Âm, nhỏ hơn 0 | x đứng trước y | x đứng trước |
| Bằng 0 | x và y tương đương theo thứ tự | Cùng vị trí logic theo so sánh |
| Dương, lớn hơn 0 | x đứng sau y | x đứng sau |

Đặc biệt, **compareTo không bắt buộc trả đúng -1, 0 hoặc 1**. Các giá trị -25, -4, 7, 25 đều hợp lệ khi phù hợp quan hệ thứ tự. Không diễn giải độ lớn của số trả về là khoảng cách giữa hai đối tượng.

Ví dụ với String:

~~~java
System.out.println("a".compareTo("z")); // -25
System.out.println("a".compareTo("a")); // 0
System.out.println("z".compareTo("a")); // 25
~~~

Với hai ký tự Latin đơn giản này, String.compareTo trả hiệu của giá trị ký tự UTF-16 đầu tiên khác nhau, nên có kết quả âm/dương với độ lớn 25.

Cách kiểm tra nên dùng:

~~~java
int result = x.compareTo(y);
if (result < 0) {
    System.out.println("x đứng trước y");
} else if (result > 0) {
    System.out.println("x đứng sau y");
} else {
    System.out.println("x tương đương y theo thứ tự");
}
~~~

Đây là mã minh họa trong ngữ cảnh đã khai báo x và y tương thích; chưa phải một chương trình chạy độc lập. **Không kiểm tra result == -1 để hiểu là nhỏ hơn**, vì kết quả -2 hoặc -25 cũng có cùng ý nghĩa. Có thể dùng Integer.signum(result) khi cần chuẩn hóa thành -1/0/1, nhưng điều đó không bắt buộc cho các nhánh điều kiện.

## 2. Comparable và Comparator cùng trả về dấu

`Comparable<T>` đặt quy tắc thứ tự tự nhiên trong kiểu dữ liệu; `Comparator<T>` xác định một thứ tự có thể truyền từ bên ngoài, chẳng hạn sắp theo ngày giảm dần hoặc theo điểm. Cả hai đều dùng **dấu âm/0/dương**, nên đoạn kiểm tra `result < 0` áp dụng cho cả `x.compareTo(y)` lẫn `comparator.compare(x, y)`.

Khi dùng `TreeSet` hoặc `TreeMap` với comparator riêng, `0` còn quyết định hai phần tử/khóa có cùng vị trí logic trong cấu trúc cây. Bài đầu chương giải thích đầy đủ khi nào chọn natural ordering hay comparator.

## 3. Dấu sai khi phép trừ bị tràn số

Dấu trả về chỉ hữu ích khi phép so sánh tính đúng: `return a - b` với hai `int` có thể tràn số và làm đảo chiều quan hệ.

~~~java
int low = Integer.MIN_VALUE;
int high = Integer.MAX_VALUE;
System.out.println(low - high);                  // 1 (sai dấu để so sánh)
System.out.println(Integer.compare(low, high)); // -1
~~~

Dùng `Integer.compare`, `Long.compare` và các helper tương ứng. Bài về **tràn số trong compareTo** sẽ kiểm tra các biên `MIN_VALUE`/`MAX_VALUE`, ép `long` xuống `int` và tác động tới tính bắc cầu.

## 4. Java 17+: ví dụ đầy đủ, chạy được

Lưu thành tệp **CompareToSignDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class CompareToSignDemo {
    public static void main(String[] args) {
        Job first = new Job(3, "B");
        Job second = new Job(3, "A");
        Job third = new Job(1, "A");

        System.out.println("first vs second: " + first.compareTo(second));
        System.out.println("second vs first: " + second.compareTo(first));
        System.out.println("same value: "
                + second.compareTo(new Job(3, "A")));

        List<Job> jobs = new ArrayList<>();
        jobs.add(first);
        jobs.add(second);
        jobs.add(third);
        jobs.sort(null);
        System.out.println("sorted list: " + jobs);

        Set<Job> sortedJobs = new TreeSet<>(jobs);
        System.out.println("TreeSet<Job> size: " + sortedJobs.size());

        int low = Integer.MIN_VALUE;
        int high = Integer.MAX_VALUE;
        System.out.println("subtraction: " + (low - high));
        System.out.println("Integer.compare: " + Integer.compare(low, high));
        System.out.println("String compare z/a: " + "z".compareTo("a"));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("BigDecimal compare: " + a.compareTo(b));
        System.out.println("BigDecimal equals: " + a.equals(b));

        Set<BigDecimal> tree = new TreeSet<>();
        tree.add(a);
        tree.add(b);
        Set<BigDecimal> hash = new HashSet<>();
        hash.add(a);
        hash.add(b);
        System.out.println("TreeSet<BigDecimal> size: " + tree.size());
        System.out.println("HashSet<BigDecimal> size: " + hash.size());
    }

    record Job(int priority, String code) implements Comparable<Job> {
        Job {
            Objects.requireNonNull(code);
        }

        @Override
        public int compareTo(Job other) {
            Objects.requireNonNull(other);
            int byPriority = Integer.compare(priority, other.priority);
            if (byPriority != 0) {
                return byPriority;
            }
            return code.compareTo(other.code);
        }
    }
}
~~~

Chạy lệnh từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 CompareToSignDemo.java
java CompareToSignDemo
~~~

Kết quả stdout:

~~~text
first vs second: 1
second vs first: -1
same value: 0
sorted list: [Job[priority=1, code=A], Job[priority=3, code=A], Job[priority=3, code=B]]
TreeSet<Job> size: 3
subtraction: 1
Integer.compare: -1
String compare z/a: 25
BigDecimal compare: 0
BigDecimal equals: false
TreeSet<BigDecimal> size: 1
HashSet<BigDecimal> size: 2
~~~

**Giải thích:** first và second có priority bằng 3, code "B" đứng sau "A" nên compareTo dương. Khi đảo chiều, kết quả âm. Hai Job cùng priority và code trả 0. Sau khi sort, Job có priority 1 đứng đầu; các Job priority 3 sắp theo code A rồi B. Record Job được sinh equals/hashCode dựa trên cả hai component, phù hợp với cặp trường mà compareTo dùng.

Hai số nguyên cực trị cho thấy phép trừ tràn số trả 1 còn Integer.compare trả -1. "z".compareTo("a") trả 25, minh chứng compareTo không bị giới hạn -1/0/1. Hai BigDecimal biểu diễn cùng giá trị nhưng khác scale dẫn đến khác biệt giữa compareTo và equals, phân tích ở phần tiếp theo.

## 5. Đọc dấu đúng trong toàn bộ hợp đồng

Ngoài dấu âm/0/dương, một `compareTo` hợp lệ còn giữ các tính chất sau trên miền đối tượng có thể so sánh:

| Quy tắc | Cần kiểm tra |
| --- | --- |
| Đảo dấu | `Integer.signum(x.compareTo(y)) == -Integer.signum(y.compareTo(x))` |
| Bắc cầu | Nếu `x > y` và `y > z` thì `x > z` |
| Giá trị tương đương | Nếu `x.compareTo(y) == 0`, dấu khi so `x` và `y` với bất kỳ `z` hợp lệ phải giống nhau |
| `null` | `x.compareTo(null)` ném `NullPointerException` |

Quy tắc đảo dấu chỉ nói về **dấu**, không yêu cầu hai kết quả có cùng trị tuyệt đối. Ví dụ `-3` và `8` vẫn trái dấu hợp lệ nếu các tính chất khác cũng được giữ. Các bài tiếp theo kiểm tra từng điều kiện bằng các cặp và bộ ba cụ thể.

## 6. Dấu 0 là tương đương theo thứ tự, không tự động là equals

`compareTo == 0` xác định hai giá trị **cùng vị trí theo thứ tự**. `equals == true` lại là bình đẳng logic của đối tượng. Java khuyến nghị mạnh hai quan hệ này nhất quán nhưng cho phép khác nhau có chủ đích.

Ví dụ, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` trong khi `equals` trả `false` do khác `scale`. Vì vậy `TreeSet<BigDecimal>` chỉ giữ một phần tử tương đương theo thứ tự, còn `HashSet<BigDecimal>` giữ hai phần tử theo `equals/hashCode`. Chương trình ở mục 4 quan sát cùng sự khác biệt này; bài về `equals` và `compareTo` phía sau hướng dẫn chọn hợp đồng đúng.

## 7. So sánh nhiều trường: xử lý hòa đúng cách

Mẫu chuẩn để so theo trường đầu, sau đó đến trường thứ hai:

~~~java
// Trích đoạn trong lớp Person có lastName, firstName là String không null.
@Override
public int compareTo(Person other) {
    int byLast = lastName.compareTo(other.lastName);
    if (byLast != 0) {
        return byLast;
    }
    return firstName.compareTo(other.firstName);
}
~~~

Nếu so sánh khóa trước trả **bất kỳ giá trị khác 0 nào**, hãy trả luôn; chỉ so khóa tiếp theo khi bằng 0. Không kiểm tra byLast == -1 hoặc byLast == 1. Nếu trường có thể null, dùng Comparator.nullsFirst/nullsLast hoặc xử lý rõ ràng, tránh gọi compareTo trực tiếp trên null.

Một Comparator thay thế có thể viết:

~~~java
// Minh họa trong ngữ cảnh có lớp Person và import java.util.Comparator.
Comparator<Person> byName =
        Comparator.comparing(Person::lastName)
                  .thenComparing(Person::firstName);
~~~

Với số nguyên nguyên thủy, Comparator.comparingInt và comparingLong giúp viết code gọn và tránh boxing không cần thiết. Nếu comparator được dùng trong TreeSet/TreeMap, hãy cân nhắc tác động của compare == 0 đến việc phân biệt khóa.

## 8. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| compareTo chỉ được trả -1/0/1 | Hợp đồng chỉ yêu cầu dấu | Kiểm tra < 0, == 0, > 0 |
| Dùng == -1 để nhận biết đứng trước | Bỏ sót -2, -25, ... | Kiểm tra < 0 |
| Lấy hiệu hai int hoặc long | Có thể tràn số | Integer.compare, Long.compare |
| Ép hiệu long về int | Có thể mất thông tin và đảo dấu | Long.compare |
| Coi độ lớn compareTo là khoảng cách | compareTo diễn tả thứ tự, không phải metric | Định nghĩa thước đo riêng |
| compareTo == 0 luôn đồng nghĩa equals | Không đúng với BigDecimal | Kiểm tra hợp đồng của kiểu |
| Chỉ so một khóa không đủ phân biệt | TreeSet có thể gộp giá trị khác nhau | Thêm khóa phá hòa nếu cần |
| Thiếu đối xứng hoặc bắc cầu | Sắp xếp và collection có thể sai kỳ vọng | Kiểm thử quan hệ thứ tự |
| Gọi compareTo của một trường null | Có thể NullPointerException | Chính sách null rõ ràng |
| Xem toán tử < trên float/double luôn đủ | Không xử lý đúng NaN và signed zero theo wrapper | Float.compare/Double.compare khi phù hợp |

## 9. Checklist và kiểm thử

- **Dấu:** nhỏ hơn trả âm, bằng theo thứ tự trả 0, lớn hơn trả dương.
- **Đảo chiều:** đổi thứ tự x/y thì dấu phải đảo.
- **Tự so sánh:** x.compareTo(x) == 0.
- **Bắc cầu:** các bộ ba x, y, z phải giữ thứ tự nhất quán.
- **Tương đương:** nếu x.compareTo(y) == 0, dấu khi so với cùng z phải khớp.
- **Biên số học:** thử Integer.MIN_VALUE, Integer.MAX_VALUE và long cực trị.
- **Phá hòa:** các trường trước trùng nhau phải được so bằng trường kế tiếp.
- **Null:** xác nhận chính sách xử lý null mong muốn.
- **Collections:** kiểm tra List.sort, TreeSet/TreeMap với các khóa tương đương.
- **Equals:** nếu tài liệu lớp tuyên bố thứ tự tương thích equals, kiểm tra compareTo == 0 **khi và chỉ khi** equals true.

Ví dụ assertion ngắn đặt trong ngữ cảnh đã khai báo ba đối tượng a, b, c:

~~~java
if (a.compareTo(b) >= 0) {
    throw new AssertionError("a phải đứng trước b");
}
if (b.compareTo(a) <= 0) {
    throw new AssertionError("b phải đứng sau a");
}
if (c.compareTo(c) != 0) {
    throw new AssertionError("Tự so sánh phải trả 0");
}
~~~

Những assertion này là đoạn minh họa, không phải chương trình đứng riêng; dữ liệu kiểm thử phải được chọn theo quy tắc so sánh của lớp.

## 10. Ghi nhớ

- **Âm:** đối tượng hiện tại đứng trước đối số.
- **Không:** hai đối tượng tương đương theo thứ tự.
- **Dương:** đối tượng hiện tại đứng sau đối số.

Điều cần nhớ là **dấu của compareTo**, không phải độ lớn. Dùng phương thức so sánh chuẩn thay phép trừ, tuân thủ đối xứng về dấu và tính bắc cầu, xử lý đúng nhiều khóa và hiểu rõ quan hệ compareTo == 0 với equals khi làm việc với TreeSet/TreeMap.