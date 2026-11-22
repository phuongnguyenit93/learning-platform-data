# Predicate.and(), or(), negate() và đánh giá ngắn mạch trong Java

## 1. Vì sao cần kết hợp Predicate?

Trong Java, **java.util.function.Predicate<T>** là functional interface biểu diễn một điều kiện trên giá trị kiểu T. Phương thức trừu tượng chức năng (SAM) của nó là **boolean test(T value)**. Vì có một SAM, ta có thể xây dựng Predicate bằng lambda hoặc method reference.

Một quy tắc nghiệp vụ thường không chỉ có một điều kiện. Chẳng hạn, một đơn hàng đủ điều kiện giao miễn phí khi **đã thanh toán**, **giao nội địa** và **đạt ngưỡng tiền**. Nếu viết tất cả trong một biểu thức, logic có thể trở nên dài và khó kiểm thử. Ta có thể tách từng điều kiện thành Predicate độc lập rồi kết hợp:

~~~java
Predicate<Order> paid = Order::paid;
Predicate<Order> domestic = Order::domestic;
Predicate<Order> minimum = order -> order.totalCents() >= 100_000L;

Predicate<Order> eligible = paid.and(domestic).and(minimum);
~~~

Đây là **đoạn minh họa**, giả định kiểu Order có các phương thức tương ứng và đã import java.util.function.Predicate. Khi dùng **eligible.test(order)**, Java đánh giá các Predicate theo thứ tự và áp dụng phép AND logic.

Ba phương thức **and()**, **or()**, **negate()** là các phép kết hợp Predicate được Java cung cấp dưới dạng **default method**:

- **p.and(q)** tạo Predicate có ý nghĩa **p(x) && q(x)**.
- **p.or(q)** tạo Predicate có ý nghĩa **p(x) || q(x)**.
- **p.negate()** tạo Predicate có ý nghĩa **!p(x)**.

Các phép này trả **một Predicate mới** đại diện cho phép kết hợp. Việc tạo Predicate kết hợp **không tự gọi test()**, không lọc dữ liệu ngay và không cần có giá trị đầu vào tại thời điểm tạo. Kết quả boolean chỉ xuất hiện khi **test(value)** được thực thi hoặc khi một API như Stream.filter cần đánh giá điều kiện.

## 2. Hiểu hợp đồng của ba phương thức

Hình dạng sử dụng:

~~~java
Predicate<T> combinedAnd = p.and(q);
Predicate<T> combinedOr = p.or(q);
Predicate<T> opposite = p.negate();
~~~

Các biến p và q ở đây là Predicate<T> đã được khởi tạo; đoạn trên chỉ minh họa API, không phải chương trình độc lập.

| Phép kết hợp | Điều kiện trả true | Điều kiện trả false | Thứ tự gọi |
| --- | --- | --- | --- |
| **p.and(q)** | Cả p(x) và q(x) đều true | Một trong hai false | Gọi p trước; chỉ gọi q nếu p true |
| **p.or(q)** | Có ít nhất một trong hai true | Cả hai false | Gọi p trước; chỉ gọi q nếu p false |
| **p.negate()** | p(x) false | p(x) true | Gọi p một lần rồi đảo boolean |

**and() và or() dùng đánh giá ngắn mạch (short-circuit)**, giống toán tử **&&** và **||** của Java. Điều đó không chỉ ảnh hưởng kết quả boolean, mà còn ảnh hưởng việc kiểm tra null, chi phí tính toán, ngoại lệ và side effect.

**negate() không có vế phải để bỏ qua**: nó gọi Predicate gốc rồi đảo kết quả. Khi Predicate gốc ném exception, negate không chuyển exception thành false/true; exception vẫn truyền ra ngoài.

### 2.1. Bảng chân trị

| p(x) | q(x) | p.and(q) | p.or(q) | p.negate() |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

Bảng là kết quả logic thuần. **Nó không nói rằng q luôn được gọi.** Trong hàng p=false với phép AND, q hoàn toàn không được đánh giá; trong hàng p=true với phép OR, q cũng không được đánh giá.

## 3. Đánh giá ngắn mạch của and(): dừng khi điều kiện đầu sai

Giả sử ta muốn xác định một chuỗi không null, không rỗng và bắt đầu bằng chữ J:

~~~java
Predicate<String> notNull = text -> text != null;
Predicate<String> notBlank = text -> !text.isBlank();
Predicate<String> startsWithJ = text -> text.startsWith("J");

Predicate<String> valid = notNull.and(notBlank).and(startsWithJ);
~~~

Đây là đoạn minh họa cần import Predicate. Nếu chạy **valid.test(null)**:

1. **notNull.test(null)** trả false.
2. Vì kết quả trái của phép **and** là false, Java **không gọi notBlank**.
3. Phép kết hợp ngoài cũng nhận false và **không gọi startsWithJ**.
4. Kết quả cuối là false, không có NullPointerException do isBlank() hoặc startsWith().

**Thứ tự rất quan trọng.** Nếu đặt **notBlank.and(notNull)** rồi truyền null, **notBlank.test(null)** sẽ gọi **null.isBlank()** và ném NullPointerException *trước khi* tới phép kiểm tra null. Do đó, các tiền điều kiện rẻ và quan trọng như **x != null** thường nên đặt ở đầu chuỗi AND.

Với logic tổng quát:

~~~text
p.and(q).test(x)

đánh giá p(x)
  ├─ false → trả false ngay; không gọi q(x)
  └─ true  → đánh giá q(x), trả kết quả q(x)
~~~

Điều này giúp tránh công việc không cần thiết. Ví dụ, có thể kiểm tra trạng thái cơ bản trước khi thực hiện phép tra cứu tốn chi phí. Tuy nhiên, việc đặt rule có side effect ở vị trí có thể bị bỏ qua phải được cân nhắc theo hợp đồng nghiệp vụ.

## 4. Đánh giá ngắn mạch của or(): dừng khi điều kiện đầu đúng

Với điều kiện một khách hàng được ưu tiên nếu thuộc nhóm VIP **hoặc** đang có voucher:

~~~java
Predicate<Customer> vip = Customer::vip;
Predicate<Customer> hasVoucher = Customer::hasVoucher;

Predicate<Customer> priority = vip.or(hasVoucher);
~~~

Đây là đoạn minh họa giả định có kiểu Customer và các accessor tương ứng.

Nếu **vip.test(customer)** trả true, toàn bộ **priority.test(customer)** trả true và **hasVoucher.test(customer)** không được gọi. Nếu vip false, Java mới hỏi điều kiện voucher.

~~~text
p.or(q).test(x)

đánh giá p(x)
  ├─ true  → trả true ngay; không gọi q(x)
  └─ false → đánh giá q(x), trả kết quả q(x)
~~~

Khi cả hai rule chỉ đọc dữ liệu và không có side effect, ngắn mạch thường mang lại lợi ích hiệu năng. Nhưng nếu rule thứ hai phải luôn chạy để ghi audit, cập nhật trạng thái hoặc trả lỗi bắt buộc, **or() không phải công cụ đúng**: rule thứ hai có thể không chạy.

**Lưu ý phân biệt:** Toán tử nhị phân **|** và **&** trên boolean trong Java có thể đánh giá cả hai vế, còn **||** và **&&** là short-circuit. Predicate.or() và Predicate.and() theo nghĩa ngắn mạch; không có phương thức Predicate tương ứng để ép hai rule phải luôn chạy.

## 5. negate(): phủ định một quy tắc

**p.negate()** được dùng để diễn đạt “không thỏa p”:

~~~java
Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = blank.negate();
~~~

Đoạn minh họa cần import Predicate; **notBlank.test("Java")** trả true, còn **notBlank.test("   ")** trả false.

Nhưng **blank.test(null)** gọi phương thức instance **isBlank()** trên null và ném NullPointerException. Do đó, **notBlank.test(null)** cũng ném lỗi. **negate() chỉ đảo kết quả boolean khi test() trả về bình thường; nó không biến exception thành true.**

Để chủ động xử lý null, ta cần làm rõ ngữ nghĩa:

~~~java
Predicate<String> present = text ->
        text != null && !text.isBlank();

Predicate<String> absent = present.negate();
~~~

Giờ **present.test(null)** trả false và **absent.test(null)** trả true. Đây là **một lựa chọn nghiệp vụ**: null được xem là “không hiện diện”. Nếu null là dữ liệu không hợp lệ phải bị từ chối, nên chủ động kiểm tra và ném exception thay vì âm thầm coi null là false.

### 5.1. Predicate.not(...) từ Java 11

Java còn cung cấp phương thức static **Predicate.not(Predicate<T>)**, giúp viết phủ định ở chỗ cần truyền Predicate vào API nhận callback:

~~~java
List<String> result = List.of("A", "", "B")
        .stream()
        .filter(Predicate.not(String::isBlank))
        .toList();
~~~

Đây là đoạn minh họa cần import **java.util.List** và **java.util.function.Predicate**. Kết quả là **["A", "B"]** theo thứ tự gặp. **Predicate.not(...)** và **p.negate()** cùng biểu thị phủ định, nhưng cách viết khác: một bên là static factory nhận Predicate, một bên là default method của Predicate đã có.

**Predicate.not(null)** sẽ ném NullPointerException theo yêu cầu tham số khác null, không tạo ra một Predicate “luôn true”. Với input null đi vào lambda **String::isBlank**, lỗi khi đánh giá vẫn có thể xảy ra nếu chưa có quy tắc loại null trước đó.

## 6. Ví dụ Java 17 hoàn chỉnh: kết hợp bộ lọc chuỗi

Tạo tệp **PredicateBasicsDemo.java**:

~~~java
import java.util.function.Predicate;

public class PredicateBasicsDemo {
    public static void main(String[] args) {
        Predicate<String> notBlank =
                text -> text != null && !text.isBlank();

        Predicate<String> startsWithJ =
                text -> text != null && text.startsWith("J");

        Predicate<String> atMostFiveChars =
                text -> text != null && text.length() <= 5;

        Predicate<String> accepted =
                notBlank.and(startsWithJ).and(atMostFiveChars);

        Predicate<String> exciting =
                startsWithJ.or(text ->
                        text != null && text.endsWith("!"));

        Predicate<String> notStartingWithJ =
                startsWithJ.negate();

        System.out.println("Java: " + accepted.test("Java"));
        System.out.println("JavaScript: "
                + accepted.test("JavaScript"));
        System.out.println("Kotlin: " + accepted.test("Kotlin"));
        System.out.println("null: " + accepted.test(null));
        System.out.println("Exciting: " + exciting.test("Hi!"));
        System.out.println("Not J: "
                + notStartingWithJ.test("Kotlin"));
        System.out.println("Not J null: "
                + notStartingWithJ.test(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 PredicateBasicsDemo.java
java PredicateBasicsDemo
~~~

Stdout:

~~~text
Java: true
JavaScript: false
Kotlin: false
null: false
Exciting: true
Not J: true
Not J null: true
~~~

**Phân tích:**

- **Java** không blank, bắt đầu bằng J và có bốn ký tự, nên được chấp nhận.
- **JavaScript** thỏa hai điều kiện đầu nhưng quá năm ký tự.
- **Kotlin** bị chặn ở **startsWithJ**, không phải xét tiếp độ dài.
- **null** bị chặn ngay ở notBlank; Predicate đã được viết null-safe nên không ném lỗi.
- **Hi!** không bắt đầu bằng J nhưng kết thúc bằng dấu **!**, nên phép OR trả true.
- **notStartingWithJ** là phủ định của Predicate có thiết kế trả false với null; vì vậy nó trả true với null. Kết quả này **không phải hợp đồng “chuỗi hợp lệ”** — nó chỉ đúng với nghĩa logic của phép phủ định.

Ví dụ nhấn mạnh rằng **phủ định của một điều kiện không đồng nghĩa với tính hợp lệ của đầu vào**. Nếu ứng dụng cần “không bắt đầu bằng J nhưng vẫn không null”, dùng **notBlank.and(startsWithJ.negate())** hoặc một Predicate có hợp đồng tương ứng.

## 7. Quan sát chính xác thứ tự gọi và nhánh bị bỏ qua

Một cách học short-circuit hiệu quả là gắn log vào các Predicate để quan sát. Cách này chỉ dành cho **demo hoặc chẩn đoán**; trong code nghiệp vụ, dùng Predicate thuần (không side effect) sẽ an toàn và dễ kiểm thử hơn.

Tạo tệp **PredicateShortCircuitDemo.java**:

~~~java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> longEnough = text -> {
            System.out.println("length: " + text);
            return text.length() > 3;
        };

        Predicate<String> startsWithJ = text -> {
            System.out.println("starts: " + text);
            return text.startsWith("J");
        };

        Predicate<String> endsWithA = text -> {
            System.out.println("ends: " + text);
            return text.endsWith("a");
        };

        Predicate<String> all =
                longEnough.and(startsWithJ).and(endsWithA);

        System.out.println("AND Java:");
        System.out.println("result: " + all.test("Java"));

        System.out.println("AND Jo:");
        System.out.println("result: " + all.test("Jo"));

        Predicate<String> either =
                startsWithJ.or(endsWithA);

        System.out.println("OR Java:");
        System.out.println("result: " + either.test("Java"));

        System.out.println("OR Luna:");
        System.out.println("result: " + either.test("Luna"));

        System.out.println("NEGATE Jo:");
        System.out.println("result: "
                + longEnough.negate().test("Jo"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
~~~

Stdout chính xác:

~~~text
AND Java:
length: Java
starts: Java
ends: Java
result: true
AND Jo:
length: Jo
result: false
OR Java:
starts: Java
result: true
OR Luna:
starts: Luna
ends: Luna
result: true
NEGATE Jo:
length: Jo
result: true
~~~

Quan sát được:

1. Với **all.test("Java")**, ba Predicate lần lượt chạy và đều true.
2. Với **all.test("Jo")**, điều kiện độ dài trả false, nên **startsWithJ** và **endsWithA** không chạy.
3. Với **either.test("Java")**, điều kiện đầu true nên không gọi **endsWithA**.
4. Với **either.test("Luna")**, điều kiện đầu false nên điều kiện thứ hai chạy, trả true.
5. Với **longEnough.negate().test("Jo")**, chỉ longEnough chạy một lần; kết quả false của nó bị đảo thành true.

Trong chương trình này không truyền null vì **longEnough**, **startsWithJ** và **endsWithA** cố ý không có null guard. Muốn hỗ trợ null, hãy đặt Predicate kiểm tra null ở đầu phép AND hoặc viết từng Predicate an toàn với null; không được dựa vào log để bảo đảm an toàn.

## 8. Thứ tự kết hợp, nhóm biểu thức và độ ưu tiên

Giống boolean trong Java, cách đặt ngoặc ảnh hưởng ý nghĩa.

~~~java
Predicate<T> rule1 = p.and(q.or(r));
Predicate<T> rule2 = p.and(q).or(r);
~~~

Đây là **biểu thức minh họa**, với p, q, r là Predicate<T> hợp lệ.

Hai quy tắc tương ứng:

~~~text
rule1(x) = p(x) && (q(x) || r(x))
rule2(x) = (p(x) && q(x)) || r(x)
~~~

Chúng **không tương đương**. Nếu p false và r true, rule1 false, còn rule2 true. Khi dịch một biểu thức nghiệp vụ có nhiều AND/OR, hãy ghi rõ ý định nhóm thay vì chỉ ghép từng phương thức để code ngắn nhất.

**Chuỗi gọi theo dấu chấm được kết hợp theo cú pháp phương thức.** Biểu thức **p.and(q).or(r)** được hiểu là **(p.and(q)).or(r)**; không dùng quy tắc ưu tiên toán tử **&&** và **||** để tự suy lại khác đi.

### 8.1. Định luật De Morgan

Nếu các Predicate được xem như điều kiện boolean thuần:

~~~text
!(p && q) = (!p || !q)
!(p || q) = (!p && !q)
~~~

Trong Java, có thể diễn đạt:

~~~java
Predicate<T> notBoth = p.and(q).negate();
Predicate<T> eitherNot = p.negate().or(q.negate());

Predicate<T> neither = p.or(q).negate();
Predicate<T> bothNot = p.negate().and(q.negate());
~~~

Đây là đoạn minh họa với p, q có kiểu Predicate<T>. Bốn Predicate mô tả hai cặp giá trị boolean tương đương về mặt logic khi các lần test trả kết quả bình thường.

**Cẩn trọng:** Sự tương đương về kết quả boolean không luôn bảo đảm giống về chi phí, log hoặc kết quả trong hệ thống **có side effect, trạng thái biến đổi hay phụ thuộc thời gian**. Dù cách viết giữ logic, không nên tự do đổi thứ tự Predicate làm I/O, ghi dữ liệu hoặc dựa vào đồng hồ.

### 8.2. Có thể đổi chỗ p và q không?

Về logic boolean thuần, **p && q = q && p**, **p || q = q || p**. Nhưng thứ tự gọi trong Java thay đổi:

- **p.and(q)** gọi p trước; **q.and(p)** gọi q trước.
- **p.or(q)** gọi p trước; **q.or(p)** gọi q trước.

Nếu p kiểm tra null còn q dereference tham số, đổi chỗ có thể biến trường hợp trả false thành NullPointerException. Nếu p rẻ còn q tốn chi phí, thứ tự cũng ảnh hưởng hiệu năng. Nếu một Predicate có side effect, thay đổi thứ tự có thể thay đổi hành vi ngoài kết quả boolean.

**Quy tắc thực hành:** đặt các kiểm tra tiền điều kiện và điều kiện rẻ, thuần, có khả năng loại dữ liệu ở vị trí hợp lý; quan trọng hơn là giữ nguyên **hợp đồng nghiệp vụ và thứ tự có chủ đích**.

## 9. Kết hợp Predicate với Stream.filter()

**Stream.filter(Predicate<? super T>)** nhận Predicate và giữ lại phần tử có test trả true. Tính năng kết hợp cho phép đặt tên rule một lần, tái sử dụng ở nhiều pipeline.

Tạo tệp **OrderRuleDemo.java**:

~~~java
import java.util.List;
import java.util.function.Predicate;

record Order(String id, long totalCents,
             boolean paid, boolean domestic) {}

public class OrderRuleDemo {
    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 150_000L, true, true),
                new Order("B", 160_000L, false, true),
                new Order("C", 90_000L, true, true),
                new Order("D", 120_000L, true, false),
                new Order("E", 200_000L, true, true)
        );

        Predicate<Order> paid = Order::paid;
        Predicate<Order> domestic = Order::domestic;
        Predicate<Order> minimum =
                o -> o.totalCents() >= 100_000L;

        Predicate<Order> freeShipping =
                paid.and(domestic).and(minimum);

        Predicate<Order> manualReview =
                paid.negate().or(domestic.negate());

        List<String> eligibleIds = orders.stream()
                .filter(freeShipping)
                .map(Order::id)
                .toList();

        List<String> reviewIds = orders.stream()
                .filter(manualReview)
                .map(Order::id)
                .toList();

        System.out.println("Eligible: " + eligibleIds);
        System.out.println("Review: " + reviewIds);
        System.out.println("Count: " + eligibleIds.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OrderRuleDemo.java
java OrderRuleDemo
~~~

Stdout:

~~~text
Eligible: [A, E]
Review: [B, D]
Count: 2
~~~

**Giải thích:**

- **A** và **E** đều đã thanh toán, giao nội địa và đạt ngưỡng tiền, nên đủ điều kiện.
- **B** không thanh toán; **C** chưa đạt ngưỡng; **D** không giao nội địa.
- **manualReview** trong ví dụ nghĩa là **chưa thanh toán hoặc không nội địa**. Vì vậy B và D thuộc danh sách Review; C không được đưa vào Review theo quy tắc đã định nghĩa. Đây là phân loại minh họa, không khẳng định chính sách vận chuyển thực tế.
- **Record Order** giúp tạo dữ liệu ví dụ gọn và cung cấp accessor cùng tên thành phần, nên **Order::paid**, **Order::domestic** và **Order::id** có chữ ký phù hợp.

### 9.1. Hai lớp “lười” khác nhau

**Kết hợp Predicate** xảy ra khi viết **paid.and(domestic)**, nhưng các phép test chưa chạy. Khi gọi **orders.stream().filter(freeShipping)**, Stream chỉ tạo **pipeline**; thao tác filter vẫn là *intermediate operation* và chưa duyệt dữ liệu.

Chỉ khi gọi **terminal operation** (như **toList**, **count**, **anyMatch**, **findFirst**) các phần tử mới được xử lý để tạo kết quả. Khi xử lý từng phần tử, bên trong Predicate kết hợp lại áp dụng short-circuit của and/or.

Hai cơ chế cần phân biệt:

1. **Stream laziness:** pipeline chưa thực thi trước terminal operation; một số terminal operation còn dừng sớm trên toàn stream.
2. **Predicate short-circuit:** với **một phần tử đã được kiểm tra**, vế phải của AND hoặc OR có thể bị bỏ qua.

Ví dụ **stream().filter(rule).findFirst()** có thể không cần duyệt các phần tử sau phần tử đầu tiên thỏa rule. Ngay cả với phần tử đang xét, **rule = p.and(q)** có thể không gọi q nếu p false. Tuy vậy, không nên dựa vào số lượng/lịch thứ tự side effect trong Stream pipeline như một hợp đồng, đặc biệt khi sử dụng parallel stream hoặc thay đổi pipeline.

### 9.2. Không có nghĩa là nhiều filter luôn tương đương về vận hành

Hai cách sau thường cho **cùng tập kết quả** nếu Predicate thuần và ổn định:

~~~java
stream.filter(p).filter(q)
stream.filter(p.and(q))
~~~

Đây là **biểu thức pipeline minh họa**, giả định stream, p và q có kiểu phù hợp. Trong một chuỗi tuần tự thông dụng, chúng đều chỉ giữ phần tử thỏa cả hai điều kiện, đồng thời các phần tử bị loại bởi p không cần đánh giá q.

Nhưng việc gộp **không phải lý do** để giả định mọi side effect, thời điểm exception, số lần đánh giá hay hành vi parallel đều có cam kết giống nhau trong mọi pipeline. Với quy tắc nghiệp vụ nên đặt mục tiêu **Predicate thuần, không thay đổi trạng thái và độc lập thứ tự**.

## 10. Exception, null và điều kiện có chi phí cao

### 10.1. Exception của nhánh bị bỏ qua

Nếu p false trong **p.and(q)**, q không chạy, nên exception vốn sẽ phát sinh từ q cũng không phát sinh ở lần test đó. Tương tự, nếu p true trong **p.or(q)** thì q không chạy.

Ví dụ:

~~~java
Predicate<String> safe = s -> s != null;
Predicate<String> needsText = s -> s.length() > 3;

System.out.println(safe.and(needsText).test(null)); // false
~~~

Đây là đoạn minh họa cần import Predicate. Nếu đổi thành **needsText.and(safe)**, việc đánh giá null ném NullPointerException. Short-circuit giúp xây dựng guard, nhưng chỉ khi viết đúng thứ tự.

### 10.2. Null ở đối số của and/or

Đối số **other** của **p.and(other)** và **p.or(other)** phải là Predicate hợp lệ, không được null. Theo hợp đồng API, truyền **null** làm other gây **NullPointerException ngay khi gọi and/or để tạo Predicate kết hợp**, không cần đợi **test()**:

~~~java
Predicate<String> p = s -> s.length() > 2;
// p.and(null)  → ném NullPointerException.
// p.or(null)   → ném NullPointerException.
~~~

Đây là đoạn minh họa và hai dòng chú thích chỉ hành vi; không nên đem hai lời gọi lỗi vào chương trình bình thường. Bên cạnh đó, gọi **p.negate()** cũng cần bản thân biến p là một đối tượng Predicate hợp lệ; không thể gọi phương thức trên p=null.

Phân biệt rõ **null làm other** (lỗi khi kết hợp) và **null làm input của test** (hành vi do Predicate quyết định).

### 10.3. Side effect không nên là lý do chính của Predicate

Predicate có thể về mặt kỹ thuật gọi database, gửi log hoặc sửa object. Nhưng **and/or có thể bỏ qua một nhánh**, và Stream có thể thực thi lười hay song song. Nếu mọi thao tác bắt buộc phải chạy, hãy tách phần **hành động** ra khỏi phần **ra quyết định**:

- Dùng Predicate để kiểm tra điều kiện và trả boolean.
- Dùng Consumer hoặc service method cho tác vụ có side effect bắt buộc.
- Nếu cần audit bắt buộc, hãy thiết kế nó ở ranh giới ứng dụng và xác định rõ khi nào được thực thi.

Một Predicate thuần thường dễ unit test, dễ tái sử dụng, dễ ghép và an toàn hơn khi đưa vào Stream.

### 10.4. Trạng thái biến đổi và đa luồng

Nếu Predicate đọc trường mutable hoặc phụ thuộc dữ liệu bị cập nhật đồng thời, kết quả có thể khác nhau giữa các lần test. **p.negate().negate()** biểu diễn phủ định hai lần về mặt logic, nhưng nếu p không ổn định do trạng thái ngoài, không nên suy ra hai lần đánh giá riêng biệt sẽ luôn quan sát cùng dữ liệu.

Lambda capture biến local phải theo quy tắc final/effectively final, nhưng **đối tượng** mà biến đó trỏ tới vẫn có thể mutable. Việc dùng Predicate trong parallel stream không làm việc đọc/ghi trạng thái chung tự động an toàn; cần tránh shared mutable state hoặc áp dụng đồng bộ hóa đúng.

## 11. Kiểm thử logic lẫn số lần đánh giá

Khi kiểm tra phép kết hợp, cần tách hai câu hỏi:

1. **Boolean có đúng không?** Kiểm tra bảng chân trị và các biên nghiệp vụ.
2. **Có chạy đúng những nhánh cần chạy không?** Kiểm tra short-circuit khi điều đó thuộc hợp đồng, đặc biệt với điều kiện bảo vệ null hoặc tránh tính toán đắt đỏ.

Ví dụ kiểm tra bằng bộ đếm, trong một phương thức đã import Predicate và AtomicInteger:

~~~java
AtomicInteger rightCalls = new AtomicInteger();

Predicate<String> leftFalse = text -> false;
Predicate<String> right = text -> {
    rightCalls.incrementAndGet();
    return true;
};

boolean result = leftFalse.and(right).test("value");

System.out.println(result);           // false
System.out.println(rightCalls.get()); // 0
~~~

Đây là **đoạn minh họa không độc lập**. Nó cho thấy q không được gọi khi p false trong AND. Để kiểm tra OR, thay **leftFalse** bằng Predicate luôn trả true và dùng **leftTrue.or(right)**; số lần gọi right cũng phải bằng 0.

Trong unit test thực tế, có thể assert kết quả và bộ đếm trực tiếp, đồng thời tách test **null**, **exception**, **cận ngưỡng** và **một nhánh đúng/sai**. Đừng khiến toàn bộ logic phụ thuộc vào log để phân biệt các rule; log ở đây chỉ là kỹ thuật quan sát.

### 11.1. Bảng case cho điều kiện nghiệp vụ

Với ví dụ miễn phí vận chuyển:

| Thanh toán | Nội địa | Đạt ngưỡng | freeShipping |
| --- | --- | --- | --- |
| true | true | true | true |
| false | true | true | false |
| true | false | true | false |
| true | true | false | false |
| false | false | false | false |

Ngoài bảng logic, hãy kiểm tra **bằng đúng ngưỡng**, **thấp hơn ngưỡng một đơn vị**, **null** (nếu mô hình cho phép) và dữ liệu không hợp lệ. Đặc biệt, một Predicate Boolean không tự mô tả vì sao điều kiện thất bại; nếu nghiệp vụ cần lý do từ chối, hãy thiết kế kết quả phong phú hoặc chạy quy trình kiểm tra có cấu trúc thay vì chỉ dựa vào and/or.

## 12. Những lỗi phổ biến khi ghép Predicate

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Cho rằng and/or gọi cả hai nhánh | Sai số lần gọi, thiếu audit/side effect | Nhớ quy tắc short-circuit, tách side effect bắt buộc |
| Dùng p.and(q) nhưng đặt guard null ở q | p có thể ném lỗi trước guard | Đặt guard null ở đầu hoặc viết rule null-safe |
| Nghĩ negate() biến exception thành true | Exception vẫn truyền ra; không có boolean để đảo | Xử lý lỗi theo hợp đồng, không dùng negate để che lỗi |
| Nhầm p.and(q).or(r) với p.and(q.or(r)) | Điều kiện nghiệp vụ bị đổi | Viết nhóm rõ ràng, bổ sung test các tổ hợp |
| Đổi thứ tự p và q vì tưởng không ảnh hưởng | Có thể đổi NPE, side effect, chi phí | Giữ thứ tự có chủ đích và dùng rule thuần |
| Truyền null vào and(null)/or(null) | NPE ngay lúc kết hợp | Validate các rule trước khi ghép |
| Cho rằng filter chạy ngay khi khai báo Stream | Chưa có terminal operation | Phân biệt tạo pipeline và thực thi pipeline |
| Cho rằng phủ định p nghĩa là input hợp lệ | Nếu p false với null, p.negate có thể true với null | Kết hợp thêm guard hợp lệ |
| Dùng Predicate đọc/ghi shared mutable state trong parallel stream | Kết quả không ổn định và data race | Dùng immutable/snapshot state hoặc đồng bộ hóa đúng |
| Cố nén mọi chính sách phức tạp thành boolean | Mất thông tin lý do và mức ưu tiên | Dùng kết quả nghiệp vụ có cấu trúc nếu cần |

## 13. Checklist áp dụng trong chương trình thật

Trước khi dùng **Predicate.and()**, **or()**, **negate()**:

1. Xác định mỗi Predicate đang trả true theo ý nghĩa nào; đặt tên như **isPaid**, **hasValidAddress**, **isEligible** thay vì tên mơ hồ.
2. Xác định **null có được chấp nhận hay không** và đặt guard đúng thứ tự.
3. Nhóm AND/OR theo chính sách; không dựa vào trực giác về dấu chấm để suy diễn sai ngoặc.
4. Xác nhận điều kiện được phép bỏ qua: trong phép AND, q bỏ qua nếu p false; trong OR, q bỏ qua nếu p true.
5. Nếu có chi phí lớn, cân nhắc thứ tự điều kiện nhưng không hy sinh ý nghĩa nghiệp vụ.
6. Kiểm soát exception và side effect: Predicate nên mô tả quyết định, không ngầm đảm nhận các tác vụ bắt buộc.
7. Với Stream, phân biệt **khởi tạo pipeline** và **thực thi terminal operation**; tránh suy luận về log/side effect như bảo đảm của API.
8. Test bảng chân trị, dữ liệu biên, null, exception và trường hợp cần short-circuit.

## 14. Bài tập thực hành

### Bài 1: Dự đoán các nhánh được gọi

Giả sử p trả false và q ghi log trước khi trả true. Với **p.and(q)** và **p.or(q)**, q có chạy không? Kết quả boolean mỗi biểu thức là gì?

**Đáp án:** Với AND, q không chạy và kết quả false. Với OR, q chạy và kết quả true.

### Bài 2: Đảo quy tắc null-safe

Cho **nonBlank = s -> s != null && !s.isBlank()**. **nonBlank.negate().test(null)** trả gì? Nếu muốn “chuỗi hợp lệ nhưng rỗng”, phải thiết kế lại rule ra sao?

**Gợi ý:** Phủ định nonBlank trả true với null. Nếu null phải bị loại, cần thêm Predicate kiểm tra non-null vào quy tắc đích.

### Bài 3: Tìm lỗi logic trong thứ tự nhóm

So sánh:

~~~java
Predicate<Order> first = paid.and(domestic.or(priority));
Predicate<Order> second = paid.and(domestic).or(priority);
~~~

Đây là đoạn minh họa với các Predicate đã định nghĩa. Nếu đơn chưa thanh toán nhưng priority=true, first và second có kết quả như nhau không? Hãy viết bảng chân trị cho ba điều kiện.

**Đáp án:** Không. first false do paid false; second true do nhánh priority của OR.

### Bài 4: Kiểm tra Stream lazy và short-circuit

Tạo một List chứa 5 chuỗi, dùng **filter(notBlank.and(startsWithJ))** rồi **findFirst()**. Gắn bộ đếm vào từng Predicate để quan sát dữ liệu nào được kiểm tra và nhánh nào bị bỏ qua. Sau đó thay findFirst() bằng toList() và so sánh số lần đánh giá trong pipeline tuần tự.

### Bài 5: Thiết kế nghiệp vụ cần lý do từ chối

Giả sử một hồ sơ có thể bị từ chối vì thiếu giấy tờ, quá hạn hoặc sai dữ liệu. Hãy giải thích khi nào **Predicate.and()** đủ để biểu diễn điều kiện Boolean, và khi nào nên dùng kết quả kiểu **Decision(boolean accepted, List<String> reasons)** hoặc một cấu trúc thích hợp để lưu lý do.

## 15. Ghi nhớ

**Predicate.and()** là phép AND có ngắn mạch, **Predicate.or()** là phép OR có ngắn mạch, còn **Predicate.negate()** đảo kết quả của Predicate gốc. Các phép ghép tạo ra **Predicate mới**; chúng không chạy test ngay khi khai báo.

Kết quả logic đúng là điều kiện cần, nhưng để viết Java đáng tin cậy còn phải hiểu **thứ tự đánh giá, nhánh bị bỏ qua, hợp đồng null, exception, side effect, phép nhóm và tính lazy của Stream**. Giữ mỗi quy tắc nhỏ, rõ nghĩa, không tác động phụ và được kiểm thử độc lập sẽ khiến logic kết hợp dễ đọc và dễ bảo trì hơn.