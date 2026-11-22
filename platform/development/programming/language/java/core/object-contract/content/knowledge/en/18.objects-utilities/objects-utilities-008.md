# Objects.compare() với Comparator được cung cấp trong Java

## 1. Mục đích và ý nghĩa

**java.util.Objects.compare(T a, T b, Comparator<? super T> c)** là phương thức tĩnh giúp so sánh hai tham chiếu bằng một **Comparator do người gọi cung cấp**. Đây là tiện ích hữu ích khi một kiểu có nhiều cách sắp xếp: theo tên, theo mức ưu tiên, theo thời gian, hoặc theo nhiều trường kết hợp.

Quy tắc cơ bản:

- Nếu a và b **là cùng một tham chiếu** (a == b), Objects.compare trả **0** ngay lập tức, không gọi Comparator.
- Nếu a và b **là hai tham chiếu khác nhau**, kết quả là **c.compare(a, b)**, do Comparator quyết định.
- Dấu của giá trị int trả về diễn đạt thứ tự: **âm** nghĩa là a đứng trước b, **0** nghĩa là tương đương theo Comparator, **dương** nghĩa là a đứng sau b.
- Comparator được truyền vào **không bắt buộc là thứ tự tự nhiên** của kiểu đối tượng. Chính người gọi chọn chính sách so sánh.

Trong hợp đồng Comparator, không bắt buộc chỉ trả -1, 0, 1; mọi số int mang dấu phù hợp đều hợp lệ. Do vậy hãy kiểm tra result < 0, result == 0 và result > 0 khi xử lý kết quả.

## 2. Chữ ký API và cơ chế thực thi

Chữ ký tổng quát của Java:

~~~java
public static <T> int compare(
        T a,
        T b,
        Comparator<? super T> c)
~~~

Cách hình dung hành vi, tương đương với logic API:

~~~java
// Mã mô phỏng cơ chế, không phải phương thức độc lập để dán vào lớp.
return (a == b) ? 0 : c.compare(a, b);
~~~

Kiểm tra a == b **so sánh danh tính tham chiếu**, không gọi a.equals(b). Điều này tạo điểm khác biệt đáng chú ý: hai đối tượng cùng giá trị theo equals nhưng **không cùng tham chiếu** vẫn được chuyển tới Comparator.

Ví dụ:

~~~java
String x = new String("java");
String y = new String("java");

// x.equals(y) true nhưng x == y false.
// String.CASE_INSENSITIVE_ORDER vẫn được gọi:
int result = Objects.compare(x, y, String.CASE_INSENSITIVE_ORDER);
~~~

Kết quả result là 0 vì Comparator xét hai chuỗi bằng nhau không phân biệt hoa/thường. Trong ví dụ này, kết quả bằng 0 đến từ Comparator, **không phải** nhánh tối ưu a == b.

Cần import java.util.Objects và java.util.Comparator cho các đoạn ví dụ riêng ở phần này.

### Vai trò của tham số kiểu

- T là kiểu của hai giá trị được so sánh.
- Comparator<? super T> cho phép dùng Comparator của T hoặc kiểu cha phù hợp.
- Phương thức trả về int; số nguyên này chỉ biểu đạt **dấu so sánh**, không phải độ đo khoảng cách.
- Khi cần dùng nhiều quy tắc sắp xếp cho một loại đối tượng, truyền Comparator khác nhau vào cùng phương thức Objects.compare.

## 3. So sánh cùng tham chiếu và khác tham chiếu

Xét ba tình huống:

| Hai đối số | Nhánh xử lý | Kết quả |
| --- | --- | --- |
| a và b trỏ chính xác cùng một đối tượng | Không gọi c.compare | Trả 0 |
| a và b là hai đối tượng riêng, dù a.equals(b) là true | Gọi c.compare(a, b) | Phụ thuộc Comparator |
| a và b là hai đối tượng riêng, a.equals(b) là false | Gọi c.compare(a, b) | Phụ thuộc Comparator |

Hành vi trả 0 khi cùng tham chiếu thể hiện một tối ưu hợp lý với Comparator tuân thủ hợp đồng: một đối tượng không đứng trước hoặc sau chính nó.

Tuy nhiên **Objects.compare không sửa được một Comparator sai hợp đồng**. Nếu Comparator ngẫu nhiên, phi bắc cầu hoặc trả kết quả trái chiều cho các cặp khác nhau, Objects.compare vẫn chuyển kết quả sai đó trở về người gọi. Việc bỏ qua lời gọi Comparator khi cùng tham chiếu cũng có nghĩa các tác dụng phụ hoặc bộ đếm bên trong Comparator không chạy trong trường hợp này. Comparator lý tưởng nên thuần túy và không phụ thuộc số lần được gọi.

**Khác biệt với Objects.equals:** Objects.equals(a, b) kiểm tra bằng nhau theo Object.equals một cách an toàn với null; Objects.compare(a, b, c) xác định **thứ tự theo Comparator được cung cấp**. Giá trị compare == 0 không tự động có nghĩa equals == true.

## 4. Trường hợp null: cần hiểu ranh giới xử lý

Objects.compare có một tình huống đặc biệt:

~~~java
Objects.compare(null, null, comparator); // 0
~~~

Khi cả hai đối số đều null, chúng có cùng tham chiếu, nên phương thức trả 0 ngay, **không gọi Comparator**.

Nhưng với đúng một đối số null:

~~~java
Objects.compare(null, item, comparator);
Objects.compare(item, null, comparator);
~~~

Khi đó a != b và Comparator được gọi với một đối số null. Objects.compare **không tự chọn null đứng trước hay sau**, cũng không tự bảo đảm null được hỗ trợ. Nếu Comparator không chấp nhận null thì có thể ném NullPointerException.

Cách chủ động đặt chính sách null:

~~~java
// null trước mọi giá trị khác null:
Comparator<String> nullFirst =
        Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER);

// null sau mọi giá trị khác null:
Comparator<String> nullLast =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER);

int firstResult = Objects.compare(null, "A", nullFirst); // -1
int lastResult = Objects.compare(null, "A", nullLast);   // 1
int bothNull = Objects.compare(null, null, nullFirst);   // 0
~~~

Các kết quả minh họa -1, 1, 0 này là xác định đối với Comparator.nullsFirst/nullsLast chuẩn; điều tổng quát cần dựa vào vẫn là dấu.

Nếu truyền c = null, **đừng xem đó là cơ chế chọn thứ tự mặc định**. Với hai tham chiếu khác nhau, phương thức sẽ cố gọi c.compare và phát sinh NullPointerException. Với hai tham chiếu giống nhau, nhánh trả 0 có thể không đụng đến c, nhưng đó không phải cách sử dụng có ý nghĩa để thay thế Comparator.

## 5. Java 17+: chương trình đầy đủ và kết quả

Lưu vào tệp **ObjectsCompareDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ObjectsCompareDemo {
    record Ticket(int priority, String code) {
        Ticket {
            Objects.requireNonNull(code);
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket(1, "A");
        Ticket second = new Ticket(2, "B");
        Ticket sameValue = new Ticket(1, "A");

        Comparator<Ticket> byPriorityThenCode =
                Comparator.comparingInt(Ticket::priority)
                          .thenComparing(Ticket::code);

        System.out.println("same reference: "
                + Objects.compare(first, first, byPriorityThenCode));
        System.out.println("first before second: "
                + Objects.compare(first, second, byPriorityThenCode));
        System.out.println("second after first: "
                + Objects.compare(second, first, byPriorityThenCode));
        System.out.println("same value is same reference: "
                + (first == sameValue));
        System.out.println("same value equals: "
                + first.equals(sameValue));
        System.out.println("same value comparison: "
                + Objects.compare(first, sameValue, byPriorityThenCode));

        Ticket laterCode = new Ticket(1, "Z");
        System.out.println("same priority, code Z vs A: "
                + Objects.compare(laterCode, first, byPriorityThenCode));

        Comparator<Ticket> byPriorityOnly =
                Comparator.comparingInt(Ticket::priority);
        System.out.println("priority only comparison: "
                + Objects.compare(first, laterCode, byPriorityOnly));
        System.out.println("different tickets equals: "
                + first.equals(laterCode));

        System.out.println("both null: "
                + Objects.compare(null, null, byPriorityThenCode));
        System.out.println("nullsFirst: "
                + Objects.compare(null, first,
                        Comparator.nullsFirst(byPriorityThenCode)));
        System.out.println("nullsLast: "
                + Objects.compare(null, first,
                        Comparator.nullsLast(byPriorityThenCode)));
        System.out.println("reversed: "
                + Objects.compare(first, second,
                        byPriorityThenCode.reversed()));

        List<Ticket> tickets = new ArrayList<>(List.of(second, first));
        tickets.sort(byPriorityThenCode);
        System.out.println("sorted: " + tickets);

        AtomicInteger callCount = new AtomicInteger();
        Comparator<Ticket> countingComparator = (left, right) -> {
            callCount.incrementAndGet();
            return byPriorityThenCode.compare(left, right);
        };
        Objects.compare(first, first, countingComparator);
        System.out.println("calls after same reference: "
                + callCount.get());
        Objects.compare(first, sameValue, countingComparator);
        System.out.println("calls after different reference: "
                + callCount.get());
    }
}
~~~

Biên dịch và chạy ở thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ObjectsCompareDemo.java
java ObjectsCompareDemo
~~~

Stdout chính xác:

~~~text
same reference: 0
first before second: -1
second after first: 1
same value is same reference: false
same value equals: true
same value comparison: 0
same priority, code Z vs A: 25
priority only comparison: 0
different tickets equals: false
both null: 0
nullsFirst: -1
nullsLast: 1
reversed: 1
sorted: [Ticket[priority=1, code=A], Ticket[priority=2, code=B]]
calls after same reference: 0
calls after different reference: 1
~~~

**Đọc kết quả:**

1. Hai tham chiếu first/first cùng đối tượng nên Objects.compare trả 0. Hai tham chiếu first/sameValue khác đối tượng, dù record equals true, nên vẫn phải gọi Comparator; kết quả 0 do cùng priority và code.
2. Comparator theo priority rồi code trả âm khi first đứng trước second, dương ở chiều ngược lại. Với priority bằng nhau, String.compareTo giữa "Z" và "A" trả 25: minh chứng không giới hạn -1/0/1.
3. byPriorityOnly trả 0 cho first và laterCode vì cùng priority, trong khi hai record có code khác nhau nên equals false. Comparator định nghĩa **tương đương theo thứ tự**, không tự động là bằng nhau về mọi thuộc tính.
4. null/null trả 0; nullsFirst và nullsLast tạo chính sách null tường minh. Comparator đảo chiều làm first đứng sau second theo thứ tự ngược.
5. Danh sách sắp tăng dần theo Comparator từ priority thấp tới cao.
6. CountingComparator là công cụ quan sát lời gọi: với first/first, count vẫn 0; với first/sameValue, count tăng lên 1 dù equals true. Trong code nghiệp vụ, tránh để logic so sánh phụ thuộc bộ đếm/tác dụng phụ này.

## 6. Comparator được cung cấp quyết định quan hệ bằng nhau theo thứ tự

Giả sử hai Ticket có cùng priority = 1 nhưng code khác nhau:

- Với Comparator.comparingInt(Ticket::priority), compare trả 0: chúng **tương đương khi sắp theo priority**.
- Với Comparator.comparingInt(...).thenComparing(Ticket::code), compare khác 0: code trở thành khóa phá hòa.
- Object.equals của record Ticket dùng cả priority và code, nên hai Ticket khác code không bằng nhau theo equals.

Điều này quan trọng trong các collection:

**List.sort(comparator)** sắp xếp danh sách theo Comparator và **không loại** phần tử có kết quả compare == 0.

**TreeSet(comparator)** hoặc **TreeMap(comparator)** dùng compare == 0 để xác định hai khóa tương đương, nên một Comparator chỉ dựa trên priority có thể gộp hai Ticket khác code thành một khóa.

**HashSet** và **HashMap** dùng equals/hashCode; cùng priority nhưng code khác nhau thì hai record Ticket là hai giá trị khác nhau.

Nếu dùng Comparator tùy chỉnh cho TreeSet/TreeMap, hãy xác định liệu compare == 0 có được kỳ vọng tương đương với equals hay không. Một Comparator hợp lệ vẫn có thể không nhất quán với equals; hệ quả là cách tập có thứ tự nhận diện khóa có thể khác so với tập băm.

## 7. Kết hợp nhiều khóa và chiều sắp xếp

Các nhà máy Comparator giúp truyền một quy tắc rõ ràng vào Objects.compare:

~~~java
Comparator<Ticket> ascending =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::code);

Comparator<Ticket> descending = ascending.reversed();

int result = Objects.compare(a, b, descending);
~~~

Đây là đoạn mã đặt trong ngữ cảnh có kiểu Ticket, đối tượng a và b, không phải chương trình độc lập. ascending so priority tăng rồi code tăng. descending đảo toàn bộ kết quả so sánh; nếu chỉ muốn đảo priority mà vẫn giữ code tăng, cần kết hợp từng tiêu chí theo mong muốn.

Ví dụ khi so sánh String:

~~~java
int caseSensitive =
        Objects.compare("java", "JAVA", Comparator.naturalOrder());
int ignoreCase =
        Objects.compare("java", "JAVA", String.CASE_INSENSITIVE_ORDER);
~~~

caseSensitive là số **dương** do ký tự thường đứng sau chữ hoa theo thứ tự String; ignoreCase là **0**. Điều này không có nghĩa String.equals mặc định coi "java" và "JAVA" là bằng nhau; đây là hai quan hệ do hai Comparator khác nhau tạo ra.

Khi trường khóa là số, ưu tiên Comparator.comparingInt, comparingLong, comparingDouble hoặc các hàm Integer.compare/Long.compare. Đừng tự tính hiệu số để quyết định thứ tự vì phép trừ có thể tràn số, nhất là với int/long cực trị.

## 8. Hợp đồng Comparator vẫn phải được duy trì

Objects.compare **không xác minh** Comparator hợp lệ. Comparator do bạn cung cấp vẫn cần thỏa các điều kiện:

1. **Đối xứng về dấu:** dấu của compare(a, b) phải ngược dấu của compare(b, a).
2. **Bắc cầu:** nếu a > b và b > c thì a > c.
3. **Tính ổn định của nhóm tương đương:** nếu compare(a, b) == 0 thì so a với z và b với z phải cho cùng dấu.
4. **Dữ liệu so sánh ổn định:** kết quả không được dao động tùy thời gian, ngẫu nhiên, hay bộ đếm khi thông tin so sánh không đổi.
5. **Quy tắc null rõ ràng:** nếu Comparator hỗ trợ null, phải áp dụng nhất quán và phù hợp các điều kiện trên.

Đặc biệt, không nên viết một Comparator chỉ kiểm tra dấu bằng biểu thức a.priority - b.priority khi các trường là int; phép trừ có thể tràn làm đảo quan hệ. Hãy dùng Integer.compare hoặc Comparator.comparingInt.

Khi Comparator không tương thích với Object.equals, điều này có thể là lựa chọn chủ ý để nhóm theo một trường; tuy nhiên phải hiểu ảnh hưởng đến sorted collection và không tuyên bố compare == 0 chắc chắn kéo theo equals true.

## 9. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ Objects.compare tự dùng thứ tự tự nhiên | Thiếu Comparator và hiểu sai hành vi | Luôn cung cấp Comparator phù hợp |
| Nghĩ Objects.compare dùng a.equals(b) để bỏ qua so sánh | Hai đối tượng equals true nhưng khác tham chiếu vẫn đi qua Comparator | Nhớ nhánh tối ưu là a == b |
| Truyền Comparator không hỗ trợ null khi một đối số null | Có thể ném NullPointerException | Dùng Comparator.nullsFirst/nullsLast |
| Cho rằng Objects.compare(null, null, c) gọi c.compare | Thực tế trả 0 sớm | Đừng dựa vào tác dụng phụ của Comparator |
| Xem compare == 0 là equals true | Sai nếu Comparator chỉ xét một phần dữ liệu | Tách quan hệ so sánh và equals |
| Kiểm tra result == -1 hoặc result == 1 | Có thể bỏ sót -25 hoặc 25 | Kiểm tra dấu result < 0 / > 0 |
| Dùng phép trừ int/long trong comparator | Tràn số và đảo dấu | Integer.compare/Long.compare |
| Comparator thay đổi theo trạng thái ngoài | Sort và TreeSet/TreeMap khó bảo đảm ổn định | Comparator thuần túy, dữ liệu khóa ổn định |
| Dùng Objects.compare để thay thế Objects.equals | So sánh thứ tự thay vì equality | Dùng API đúng mục tiêu |

Lưu ý: Objects.compare trả 0 khi cùng tham chiếu ngay cả nếu Comparator được viết bất thường; không nên tận dụng hành vi đó để né lỗi của một Comparator sai hợp đồng. Hãy sửa Comparator để quan hệ so sánh nhất quán đối với mọi cặp hợp lệ.

## 10. Kiểm thử có ý nghĩa

Để kiểm tra cách dùng Objects.compare, cần thử:

- **Cùng tham chiếu:** Objects.compare(x, x, c) trả 0.
- **Khác tham chiếu nhưng cùng giá trị:** Comparator được dùng và cho kết quả phù hợp, thông thường là 0 nếu chính sách xét cùng thuộc tính.
- **Nhỏ hơn/lớn hơn:** kiểm tra dấu âm hoặc dương ở cả hai chiều, không ép đúng -1/1.
- **Bằng nhau theo tiêu chí phụ:** cùng priority nhưng khác code; thử comparator chỉ priority và comparator có khóa phụ.
- **Một/both null:** với Comparator hỗ trợ null, xác nhận thứ tự; với Comparator không hỗ trợ null, xác nhận lỗi theo hợp đồng ứng dụng.
- **Đảo chiều:** reversed đảo dấu đối với các cặp không tương đương.
- **Bộ sưu tập:** List.sort giữ đủ phần tử; TreeSet có thể gộp theo compare == 0.
- **Ổn định:** cùng dữ liệu so sánh, các lần gọi nên giữ kết quả tương đương.

Ví dụ assertion trong ngữ cảnh có đối tượng x, y và Comparator c:

~~~java
int forward = Objects.compare(x, y, c);
int backward = Objects.compare(y, x, c);
if (Integer.signum(forward) != -Integer.signum(backward)) {
    throw new AssertionError("Dấu so sánh không đối xứng");
}
~~~

Đoạn này minh họa một phép kiểm tra, không phải chương trình đứng riêng; để kiểm tra bắc cầu cần thêm đối tượng thứ ba và dữ liệu thích hợp. Không so sánh forward == -backward bằng số học tuyệt đối vì có thể có kết quả Integer.MIN_VALUE không đổi được dấu an toàn theo phép trừ int; Integer.signum cho phép chỉ xét dấu.

## 11. Khi nào nên dùng và khi nào không?

**Nên dùng** Objects.compare khi cần một tiện ích ngắn để so hai tham chiếu theo Comparator rõ ràng, đặc biệt nếu muốn nhánh trả 0 nhanh cho hai tham chiếu trùng nhau, hoặc nếu code đang dùng đồng bộ các tiện ích java.util.Objects.

**Có thể gọi trực tiếp** c.compare(a, b) nếu chính sách đã rõ và muốn mọi lần so sánh đều đi qua Comparator; hai lối gọi có thể khác nhau ở trường hợp cùng tham chiếu và tác dụng phụ của Comparator. Comparator hợp lệ thông thường vẫn phải trả 0 khi so một đối tượng với chính nó.

**Không nên dùng** Objects.compare như phương thức tự động kiểm tra equality sâu, thay thế Objects.equals, hoặc tự phát hiện chính sách null/thứ tự tự nhiên. Nếu không có Comparator và kiểu có Comparable, gọi compareTo trực tiếp trong trường hợp thích hợp hoặc dùng Comparator.naturalOrder() khi cần một Comparator.

## 12. Ghi nhớ

**Objects.compare(a, b, c)** có đúng hai nhánh thực thi cốt lõi:

1. a == b: trả 0 ngay.
2. a != b: trả nguyên kết quả c.compare(a, b).

Dấu âm/0/dương luôn được hiểu **theo Comparator được cung cấp**. Hai đối tượng khác tham chiếu, dù equals true, vẫn đi qua Comparator. Không có cơ chế xử lý null toàn diện tích hợp ngoài trường hợp cùng tham chiếu; khi một đối số null, hãy chọn Comparator.nullsFirst hoặc Comparator.nullsLast nếu nghiệp vụ cho phép null. Đừng suy diễn compare == 0 luôn đồng nghĩa Object.equals true, nhất là khi dùng Comparator tùy chỉnh cùng TreeSet/TreeMap.