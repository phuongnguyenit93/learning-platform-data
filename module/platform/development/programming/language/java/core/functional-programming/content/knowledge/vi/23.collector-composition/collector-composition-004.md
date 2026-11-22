# flatMapping() để làm phẳng trong từng nhóm bằng Collector kết hợp

## 1. Bài toán: mỗi phần tử nguồn có nhiều phần tử con

Trong Java Stream API, nhiều mô hình dữ liệu có quan hệ **một-nhiều**: một đơn hàng có nhiều dòng hàng, một bài viết có nhiều nhãn, một nhân viên có nhiều kỹ năng, hoặc một dự án có nhiều công việc. Khi nhóm đối tượng cha theo khóa, ta thường muốn **gộp tất cả phần tử con của từng nhóm** thay vì nhận một danh sách lồng nhau.

Giả sử mỗi bài viết có một loại nội dung và một danh sách tag:

~~~java
record Article(String category, List<String> tags) {}
~~~

Đây là khai báo record minh họa cần import **java.util.List**.

Kết quả mong muốn có dạng:

~~~text
guide -> [java, stream, collector]
news  -> [jdk, release]
faq   -> []
~~~

Nếu dùng **Collectors.groupingBy(Article::category, Collectors.mapping(Article::tags, Collectors.toList()))**, kiểu kết quả sẽ là **Map<String,List<List<String>>>**: trong mỗi nhóm còn một danh sách tag cho từng bài viết. Muốn trực tiếp nhận **Map<String,List<String>>**, cần một phép **làm phẳng (flatten)** ở tầng downstream.

Từ Java 9, **Collectors.flatMapping(...)** giải quyết đúng bài toán này:

~~~java
Map<String, List<String>> byCategory = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        article -> article.tags().stream(),
                        Collectors.toList())));
~~~

Đây là đoạn minh họa; giả định **articles** không chứa null và mỗi **tags()** trả một List không null. Cần import **Map**, **List** và **Collectors**.

Điểm khác biệt rất quan trọng:

- **groupingBy** quyết định phần tử cha đi vào **nhóm nào**.
- **flatMapping** biến **một phần tử cha** thành **0, 1 hoặc nhiều phần tử con** và chuyển từng phần tử con cho downstream collector **trong chính nhóm đó**.
- **toList** quyết định cách các phần tử con được tích lũy: danh sách phẳng trong từng nhóm.

**Nói ngắn gọn:** `flatMapping` là một **downstream collector adapter**. Nó không phải thao tác `Stream.flatMap()` độc lập, mà được dùng như một thành phần của collector kết hợp, đặc biệt hữu ích cùng `groupingBy`, `partitioningBy` hoặc một collector khác.

## 2. Chữ ký và ý nghĩa của Collectors.flatMapping

Chữ ký khái quát của API:

~~~java
public static <T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream)
~~~

Đây là **chữ ký giải thích** trong `java.util.stream.Collectors`, không phải chương trình độc lập. Những tham số kiểu generic giúp tách rõ ba lớp trách nhiệm:

| Thành phần | Vai trò |
| --- | --- |
| **T** | Kiểu phần tử đi vào collector, ví dụ **Article** |
| **U** | Kiểu phần tử con sau khi làm phẳng, ví dụ **String** tag |
| **mapper** | Hàm nhận một T và trả **Stream<? extends U>** |
| **downstream** | Collector nhận từng U, ví dụ **toList()**, **toSet()**, **counting()** hoặc **summingLong(...)** |
| **R** | Kiểu kết quả cuối của downstream, ví dụ **List<String>**, **Set<String>**, **Long** |
| **Collector<T,?,R>** | Bộ gom mới nhìn đầu vào T và trả kết quả R |

Một điểm rất dễ sai: **mapper phải trả Stream**, không được trả trực tiếp **List** hoặc **Optional**.

~~~java
// HỢP LỆ, giả định Article.tags() trả List<String>:
article -> article.tags().stream()

// KHÔNG PHÙ HỢP với flatMapping:
// article -> article.tags()          // trả List, không phải Stream
~~~

Đây là đoạn minh họa, các biến/tên kiểu chưa được khai báo trong một chương trình độc lập.

Nếu một đối tượng có đúng một tag tùy chọn, mapper có thể trả `Optional<String>.stream()` (từ Java 9), nhưng **không** truyền thẳng Optional thay cho Stream:

~~~java
article -> article.primaryTag().stream()
~~~

Đoạn trên giả định `primaryTag()` trả một **Optional<String> không null**.

**Thời điểm xử lý:** Khi một phần tử T đi vào collector, mapper được gọi để nhận Stream<U>; từng U được chuyển tới downstream collector. Stream kết quả do mapper trả được đóng sau khi các phần tử được đưa vào downstream. Nếu mapper trả null thay vì Stream, hợp đồng của **Collectors.flatMapping** xem như **Stream rỗng**; tuy nhiên nên trả **Stream.empty()** tường minh để hợp đồng của mapper dễ hiểu và giảm rủi ro lỗi ở chỗ khác.

## 3. So sánh flatMapping và mapping: khác nhau ở tầng dữ liệu

**Collectors.mapping(f, downstream)** thực hiện ánh xạ **một T thành một U**, rồi chuyển một U đó cho downstream. Nếu U là List<String>, downstream toList sẽ nhận **một List<String> mỗi bài**.

~~~java
Map<String, List<List<String>>> nested = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.mapping(
                        Article::tags,
                        Collectors.toList())));
~~~

Đây là đoạn minh họa. Một nhóm có hai bài, mỗi bài chứa ba tag và một tag, sẽ có kết quả kiểu:

~~~text
guide -> [[java, stream, java], [collector]]
~~~

Ngược lại, **flatMapping** đi qua các phần tử của Stream con và cho:

~~~text
guide -> [java, stream, java, collector]
~~~

| Ý định | Downstream phù hợp | Kiểu giá trị mỗi nhóm |
| --- | --- | --- |
| Giữ mỗi danh sách tag nguyên vẹn | **mapping(Article::tags, toList())** | **List<List<String>>** |
| Ghép các tag thành một danh sách | **flatMapping(a -> a.tags().stream(), toList())** | **List<String>** |
| Ghép và loại tag trùng | **flatMapping(..., toSet())** | **Set<String>** |
| Ghép và giữ thứ tự gặp đầu tiên | **flatMapping(..., toCollection(LinkedHashSet::new))** | **LinkedHashSet<String>** |
| Ghép và xếp tag theo alphabet | **flatMapping(..., toCollection(TreeSet::new))** | **TreeSet<String>** |
| Đếm tổng số tag trong từng nhóm | **flatMapping(..., counting())** | **Long** |

**Không phải mọi bài toán đều nên làm phẳng.** Nếu nhiệm vụ là biết từng bài có những tag nào, danh sách lồng nhau có thể đúng. Nếu nhiệm vụ là xây một từ điển tag theo category, danh sách phẳng hoặc Set thường dễ dùng hơn.

### 3.1. Kết hợp với filtering

Khi cần loại các tag rỗng hoặc không hợp lệ, có hai cách:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream()
                .filter(tag -> tag != null && !tag.isBlank()),
        Collectors.toList())
~~~

hoặc:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.filtering(
                tag -> tag != null && !tag.isBlank(),
                Collectors.toList()))
~~~

Đây là các biểu thức collector minh họa; **Collectors.filtering** cũng được thêm trong Java 9. Cách thứ nhất lọc trong Stream con do mapper tạo. Cách thứ hai dùng một downstream collector adapter nữa, làm rõ các tầng của bộ gom.

**Về thực hành:** Nếu không cần tái sử dụng rule, lọc trong mapper thường ngắn. Nếu kiến trúc đang kết hợp nhiều downstream collector hoặc có rule dùng lại, filtering có thể rõ trách nhiệm hơn. Không dùng filter để âm thầm loại dữ liệu hỏng khi nghiệp vụ yêu cầu báo lỗi.

## 4. Chương trình Java 17: nhóm bài viết và làm phẳng tag

Tạo tệp **FlatMappingGroupsDemo.java**:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Article(String category, List<String> tags) {}

public class FlatMappingGroupsDemo {
    public static void main(String[] args) {
        List<Article> articles = List.of(
                new Article("guide",
                        List.of("java", "stream", "java")),
                new Article("news", List.of("jdk")),
                new Article("guide", List.of("collector")),
                new Article("faq", List.of()),
                new Article("news", List.of("release"))
        );

        Map<String, List<String>> allTags = articles.stream()
                .collect(Collectors.groupingBy(
                        Article::category,
                        TreeMap::new,
                        Collectors.flatMapping(
                                a -> a.tags().stream(),
                                Collectors.toList())));

        Map<String, LinkedHashSet<String>> uniqueTags =
                articles.stream()
                        .collect(Collectors.groupingBy(
                                Article::category,
                                TreeMap::new,
                                Collectors.flatMapping(
                                        a -> a.tags().stream(),
                                        Collectors.toCollection(
                                                LinkedHashSet::new))));

        System.out.println("All: " + allTags);
        System.out.println("Unique: " + uniqueTags);
        System.out.println("FAQ size: " + allTags.get("faq").size());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 FlatMappingGroupsDemo.java
java FlatMappingGroupsDemo
~~~

Stdout:

~~~text
All: {faq=[], guide=[java, stream, java, collector], news=[jdk, release]}
Unique: {faq=[], guide=[java, stream, collector], news=[jdk, release]}
FAQ size: 0
~~~

**Giải thích chính xác:**

1. **groupingBy(Article::category, TreeMap::new, downstream)** phân nhóm bài viết và trả Map có khóa category được sắp xếp tự nhiên theo **TreeMap**: faq, guide, news.
2. **flatMapping(a -> a.tags().stream(), toList())** đưa từng tag vào danh sách của category, giữ cả tag "java" lặp lại.
3. **flatMapping(..., toCollection(LinkedHashSet::new))** thay downstream bằng LinkedHashSet, loại tag trùng nhưng giữ thứ tự gặp của những tag duy nhất trong pipeline tuần tự.
4. Category **faq** vẫn có **một bài viết nguồn**, dù bài đó có danh sách tag rỗng. Vì groupingBy xử lý bài viết trước khi downstream flatMapping làm phẳng tag, khóa **faq vẫn được tạo**, với collection rỗng.
5. **TreeMap** được chọn để stdout ổn định theo khóa. `groupingBy` hai tham số mặc định không cam kết loại Map hoặc thứ tự lặp khóa, nên không nên viết expected stdout phụ thuộc một HashMap cụ thể.

**Bài học quan trọng:** `flatMapping` không làm biến mất nhóm đã có phần tử cha chỉ vì Stream con rỗng. Điều này khác với việc làm phẳng tất cả phần tử trước rồi mới nhóm, khi một cha không có con có thể mất dấu hoàn toàn.

## 5. Khác gì so với Stream.flatMap() trước groupingBy?

Hai cách dễ nhìn tương tự nhưng có thể **khác cấu trúc kết quả**.

**Cách A: Nhóm cha rồi làm phẳng trong từng nhóm**

~~~java
Map<String, List<String>> byCategory = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

**Cách B: Làm phẳng cha-con trước rồi nhóm từng con**

~~~java
record TagEntry(String category, String tag) {}

Map<String, List<String>> byCategory = articles.stream()
        .flatMap(a -> a.tags().stream()
                .map(tag -> new TagEntry(a.category(), tag)))
        .collect(Collectors.groupingBy(
                TagEntry::category,
                Collectors.mapping(
                        TagEntry::tag,
                        Collectors.toList())));
~~~

Đây là **hai đoạn minh họa độc lập** để so sánh; cần các import liên quan và đặt record ở phạm vi hợp lệ. Cách B cần một **TagEntry** để mang category của cha theo từng tag con.

Khác biệt:

- **Cách A** giữ logic nhóm trên các **Article nguồn**. Một category có bài viết nhưng tag list rỗng vẫn xuất hiện với danh sách kết quả rỗng.
- **Cách B** tạo một Stream<TagEntry>. Bài viết không có tag tạo **0 TagEntry**; category chỉ có những bài như vậy sẽ **không xuất hiện** trong kết quả groupingBy.
- **Cách A** không cần tạo đối tượng trung gian TagEntry cho từng tag.
- **Cách B** phù hợp khi cần biến đổi dữ liệu sang thực thể con có thông tin parent rõ ràng để xử lý thêm nhiều bước độc lập trước khi nhóm.
- Khi tất cả bài đều có tag và không có quy tắc đặc biệt, hai cách có thể tạo nội dung tag tương đương theo từng khóa, nhưng vẫn khác đường đi dữ liệu và chi phí.

**Đừng áp dụng quy tắc “luôn flatMap trước groupingBy”** khi yêu cầu nghiệp vụ cần giữ nhóm rỗng hoặc giữ chính xác số lượng phần tử cha đã được phân nhóm.

## 6. Nhóm rỗng: một phân biệt rất dễ bỏ qua

Hãy xét các nhóm:

~~~text
Article(category="faq", tags=[])
Article(category="guide", tags=["java"])
~~~

Nếu dùng **groupingBy + flatMapping**, nhóm faq được tạo bởi Article cha, và downstream nhận 0 tag:

~~~text
faq   -> []
guide -> [java]
~~~

Nếu dùng **Stream.flatMap() trước groupingBy**, Article faq không phát ra TagEntry nào, nên groupingBy không có bản ghi nào mang khóa faq:

~~~text
guide -> [java]
~~~

**Vì sao có sự khác biệt?** groupingBy phải nhận được một phần tử để tạo nhóm. Khi groupingBy chạy trên **Article**, bài faq đã hiện diện. Khi groupingBy chạy trên **TagEntry**, faq chỉ có thể xuất hiện nếu đã có ít nhất một TagEntry của faq.

Tình huống thực tế:

- Báo cáo số lượng kỹ năng theo phòng ban: phòng không có kỹ năng vẫn cần hiển thị **0**.
- Danh sách tag theo chuyên mục: chuyên mục có bài nhưng không có tag vẫn cần hiển thị **[]**.
- Thu thập các hạng mục chi phí theo dự án: dự án đã tồn tại nhưng không có dòng chi phí vẫn cần hiển thị trong báo cáo.

**Ngoại lệ cần phân biệt:** Nếu **không có Article cha nào** thuộc category faq, ngay cả groupingBy + flatMapping cũng không tự tạo khóa faq. Muốn báo cáo luôn có **mọi category định nghĩa trước**, cần merge với danh sách category chuẩn hoặc khởi tạo các khóa còn thiếu theo chính sách ngoài collector.

## 7. Không giới hạn downstream ở toList()

`flatMapping` biến một T thành Stream<U>, sau đó downstream có thể xử lý các U theo nhiều cách khác nhau.

### 7.1. Loại trùng với toSet()

~~~java
Map<String, Set<String>> tagsByCategory =
        articles.stream().collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toSet())));
~~~

Đây là đoạn minh họa cần import Map, Set, Collectors. **Set** loại trùng nhưng `Collectors.toSet()` không cam kết implementation cụ thể hay thứ tự duyệt. Không dùng Set nếu nghiệp vụ cần giữ tất cả số lần xuất hiện.

### 7.2. Giữ thứ tự gặp đầu tiên với LinkedHashSet

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.toCollection(LinkedHashSet::new))
~~~

Đây là biểu thức downstream minh họa cần import LinkedHashSet, Collectors. Với nguồn Stream có thứ tự gặp và thao tác thu gom thông thường, LinkedHashSet duyệt theo thứ tự chèn của các giá trị phân biệt.

### 7.3. Sắp xếp bằng TreeSet

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.toCollection(TreeSet::new))
~~~

Đoạn minh họa cần import TreeSet, Collectors. Nó chọn TreeSet; kết quả trong từng nhóm sắp xếp theo natural ordering của String và loại trùng theo comparator/natural ordering.

**Cẩn trọng:** Với các kiểu đối tượng con không Comparable hoặc có comparator trả 0 cho hai giá trị khác nhau, TreeSet có thể ném ClassCastException hoặc loại những bản ghi không mong muốn. Lựa chọn downstream quyết định cả semantics kết quả.

### 7.4. Đếm số phần tử con bằng counting()

~~~java
Map<String, Long> tagCountByCategory =
        articles.stream().collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.counting())));
~~~

Đây là đoạn minh họa. **counting()** đếm **từng phần tử con được phát ra**, bao gồm các giá trị trùng. Nếu một bài có ba tag và một bài có một tag, tổng tag trong nhóm là 4. Đừng nhầm với **Collectors.counting() trực tiếp sau groupingBy**, vốn sẽ đếm **số Article cha**.

### 7.5. Tổng hợp số bằng summingLong

Nếu một đơn hàng có nhiều dòng tiền, downstream có thể cộng `amountCents()` của từng dòng:

~~~java
Collectors.flatMapping(
        order -> order.lines().stream(),
        Collectors.summingLong(Line::amountCents))
~~~

Đây là biểu thức minh họa, giả định có record/class **Line** và **Order** với kiểu tương thích. Khi đó **R = Long**, không phải List hay Set. Bài toán "làm phẳng trong từng nhóm" có thể kết thúc bằng một số tổng, không bắt buộc một collection mới.

**Chọn đúng downstream theo nhu cầu báo cáo**, tránh tạo list trung gian lớn rồi mới duyệt lại để đếm hoặc cộng khi một collector tổng hợp đã đáp ứng đủ.

## 8. Chương trình Java 17: làm phẳng rồi tổng hợp tiền theo vùng

Tạo tệp **FlatMappingTotalsDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Line(String sku, long amountCents) {}
record Order(String region, List<Line> lines) {}

public class FlatMappingTotalsDemo {
    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("North", List.of(
                        new Line("A", 120),
                        new Line("B", 30))),
                new Order("South", List.of(
                        new Line("C", 80))),
                new Order("North", List.of(
                        new Line("D", 50))),
                new Order("West", List.of())
        );

        Map<String, Long> totals = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.flatMapping(
                                order -> order.lines().stream(),
                                Collectors.summingLong(
                                        Line::amountCents))));

        Map<String, Long> lineCounts = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.flatMapping(
                                order -> order.lines().stream(),
                                Collectors.counting())));

        System.out.println("Totals: " + totals);
        System.out.println("Lines: " + lineCounts);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FlatMappingTotalsDemo.java
java FlatMappingTotalsDemo
~~~

Stdout:

~~~text
Totals: {North=200, South=80, West=0}
Lines: {North=3, South=1, West=0}
~~~

**Giải thích kết quả:**

- North có ba dòng: A=120, B=30 và D=50; tổng **200** và count **3**.
- South có một dòng C=80; tổng **80** và count **1**.
- West có **một Order nhưng không có Line**, vẫn xuất hiện trong Map, có tổng 0 và count 0.
- `groupingBy(Order::region,...)` tạo nhóm theo vùng từ **Order cha** trước khi flatMapping làm phẳng các dòng hàng.
- Mỗi downstream `summingLong` và `counting` nhận từng **Line con**, không phải Order cha.

**Đơn vị tiền:** các số `amountCents` là ví dụ đơn vị nhỏ nhất. `summingLong` có thể tràn miền long; đối với tiền tệ thực phải chọn đơn vị và kiểm tra giới hạn phù hợp. Không dùng Long để khẳng định không thể overflow.

Một lưu ý vận hành: chương trình trên tạo **hai stream mới từ cùng List** để có hai kết quả độc lập. Nếu nguồn là cursor đọc một lần hoặc pipeline I/O tốn kém, có thể thiết kế downstream phức hợp bằng `Collectors.teeing` (Java 12+) để tạo nhiều số đo trong cùng một lượt, nhưng chỉ nên làm khi nhu cầu thật sự đòi hỏi.

## 9. Dùng Optional.stream() khi mỗi phần tử cha có tối đa một giá trị con

Không phải quan hệ một-nhiều nào cũng cần List. Nếu một tài khoản có **0 hoặc 1 mã giới thiệu**, có thể biểu diễn bằng Optional<String> và dùng **Optional.stream()** để tạo Stream 0/1 phần tử.

Tạo tệp **FlatMappingOptionalDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Account(String team, Optional<String> referralCode) {}

public class FlatMappingOptionalDemo {
    public static void main(String[] args) {
        List<Account> accounts = List.of(
                new Account("A", Optional.of("R1")),
                new Account("B", Optional.empty()),
                new Account("A", Optional.of("R2")),
                new Account("C", Optional.empty())
        );

        Map<String, List<String>> codes = accounts.stream()
                .collect(Collectors.groupingBy(
                        Account::team,
                        TreeMap::new,
                        Collectors.flatMapping(
                                account -> account.referralCode().stream(),
                                Collectors.toList())));

        System.out.println(codes);
        System.out.println("B present: " + codes.containsKey("B"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FlatMappingOptionalDemo.java
java FlatMappingOptionalDemo
~~~

Stdout:

~~~text
{A=[R1, R2], B=[], C=[]}
B present: true
~~~

**Giải thích:**

1. `Optional.of("R1").stream()` phát một String "R1".
2. `Optional.empty().stream()` phát 0 String.
3. Nhóm B và C vẫn xuất hiện vì có Account cha, dù mỗi Account không mang referralCode.
4. `TreeMap` cố định thứ tự khóa A, B, C khi in.
5. Với dữ liệu không có Account thuộc nhóm D, sẽ không có khóa D được tạo tự động.

**Đừng nhầm:** `Optional.stream()` chỉ an toàn khi `account.referralCode()` trả **Optional không null**. Nếu bản thân trường Optional là null, việc gọi `stream()` trên đó vẫn ném NPE. Trong thiết kế API, phương thức đã công bố trả Optional nên trả **Optional.empty()** khi vắng giá trị, không trả null.

## 10. Null và dữ liệu không hợp lệ: bảo vệ ở đúng tầng

Có ít nhất bốn trường hợp null cần xem xét:

1. **Phần tử cha null:** `groupingBy(Article::category)` sẽ gây NPE khi gọi accessor trên null.
2. **Khóa phân nhóm null:** `groupingBy` trong JDK yêu cầu khóa phân loại không null; nếu classifier trả null, collect ném NullPointerException.
3. **Danh sách con null:** `article.tags().stream()` sẽ ném NPE nếu tags() trả null.
4. **Phần tử con null:** nếu Stream con chứa null, `toList()` có thể tích lũy null nhưng `TreeSet`, `EnumSet` hoặc downstream dereference có thể không chấp nhận.

Một mapper null-safe rõ ràng:

~~~java
Collectors.flatMapping(
        article -> article.tags() == null
                ? Stream.<String>empty()
                : article.tags().stream()
                        .filter(Objects::nonNull),
        Collectors.toList())
~~~

Đây là biểu thức minh họa cần import Stream, Objects, Collectors, giả định Article.tags() trả List<String> có thể null. Nó biến **danh sách tags null** thành **không có tag**; mỗi tag null trong danh sách được loại riêng. Nhưng đây là **chính sách dữ liệu**, không phải thao tác sửa lỗi phổ quát.

**Cân nhắc ý nghĩa:**

- Null list có thể có nghĩa “không có tag”: `Stream.empty()` phù hợp.
- Null list có thể là lỗi do hệ thống không tải được tags: không nên lặng lẽ coi là rỗng.
- Null child có thể là bản ghi hỏng cần audit: filter sẽ làm mất dấu, nên cần cơ chế validation/reporting.
- Null key không chỉ gây lỗi ở downstream: hãy xác định classifier trả khóa không null hay thay thế bằng nhóm như **"UNKNOWN"** theo chính sách.

Đừng trông chờ `flatMapping` tự xử lý tất cả các loại null. JDK có hành vi **mapper trả null Stream** được coi là rỗng, nhưng **mapper gọi getter trên cha null** có thể ném lỗi trước khi có Stream; null trong chính Stream con cũng không được tự lọc.

### 10.1. Kiểm tra null trước khi nhóm

~~~java
articles.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

Đây là đoạn minh họa. Bước `filter(Objects::nonNull)` bảo vệ **Article null**, nhưng không bảo đảm category hay tags không null. Một pipeline an toàn phải xét **mỗi boundary** của dữ liệu theo hợp đồng.

Nếu bài toán bắt buộc tất cả Article đều hợp lệ, tốt hơn là kiểm tra và ném lỗi tại điểm nhận dữ liệu thay vì bỏ phần tử mà không ghi nhận, vì việc loại Article có thể làm sai thống kê.

## 11. Chương trình Java 17: null-safe, chuẩn hóa và Set có thứ tự

Tạo tệp **FlatMappingNullSafeDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

record Employee(String department, List<String> skills) {}

public class FlatMappingNullSafeDemo {
    static Stream<String> validSkills(Employee employee) {
        if (employee.skills() == null) {
            return Stream.empty();
        }
        return employee.skills().stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty());
    }

    public static void main(String[] args) {
        List<Employee> people = Arrays.asList(
                new Employee("IT", Arrays.asList(
                        " Java ", null, "SQL", "Java")),
                new Employee("HR", List.of()),
                new Employee("IT", null),
                new Employee("HR", List.of("Interview", "Payroll")),
                new Employee("Ops", List.of())
        );

        Map<String, TreeSet<String>> skillsByDepartment =
                people.stream()
                        .collect(Collectors.groupingBy(
                                Employee::department,
                                TreeMap::new,
                                Collectors.flatMapping(
                                        FlatMappingNullSafeDemo::validSkills,
                                        Collectors.toCollection(
                                                TreeSet::new))));

        System.out.println(skillsByDepartment);
        System.out.println("IT count: "
                + skillsByDepartment.get("IT").size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FlatMappingNullSafeDemo.java
java FlatMappingNullSafeDemo
~~~

Stdout:

~~~text
{HR=[Interview, Payroll], IT=[Java, SQL], Ops=[]}
IT count: 2
~~~

**Phân tích:**

- `Arrays.asList` cho phép phần tử null trong danh sách kỹ năng của IT; record Employee vẫn không null.
- `validSkills` chuyển List skills null thành Stream.empty(), lọc từng String null, strip khoảng trắng, loại chuỗi rỗng.
- `TreeSet` loại trùng **Java** và sắp xếp giá trị còn lại theo natural ordering.
- **HR** có một Employee không có skill và một Employee có hai skill, nên nhóm HR có hai giá trị.
- **IT** có skill "Java", "SQL", "Java"; TreeSet cho **[Java, SQL]**.
- **Ops** có một Employee nhưng danh sách skills rỗng nên khóa Ops vẫn xuất hiện với TreeSet rỗng.
- `TreeMap` khiến thứ tự hiển thị các department là HR, IT, Ops.

**Phạm vi của ví dụ:** chính sách **loại dữ liệu skills null** chỉ phù hợp khi đó là dữ liệu tùy chọn hoặc hỏng có thể bỏ theo yêu cầu. Nếu cần cảnh báo trường dữ liệu bất thường, hãy có bước xác thực và kết quả lỗi riêng trước collector.

## 12. Có thể kết hợp với partitioningBy không?

Có. **Collectors.partitioningBy(predicate, downstream)** chia nguồn thành **hai nhóm Boolean**: true và false. Downstream `flatMapping` có thể làm phẳng các phần tử con **trong từng phía**.

Ví dụ ý tưởng:

~~~java
Map<Boolean, List<String>> tags = articles.stream()
        .collect(Collectors.partitioningBy(
                Article::published,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.toList())));
~~~

Đây là đoạn minh họa, giả định Article có phương thức **published() trả boolean**, tags() trả List<String>, và các import phù hợp. Kết quả gồm:

- Khóa **true**: mọi tag của Article được xuất bản.
- Khóa **false**: mọi tag của Article chưa xuất bản.

Khác với `groupingBy`, **partitioningBy** có hợp đồng trả hai partition Boolean, kể cả khi một partition không có phần tử; downstream trả giá trị rỗng thích hợp cho partition đó. Điều này hữu ích khi cần báo cáo hai phía có mặt rõ ràng.

**Không dùng partitioningBy để nhóm đa khóa** như department hay category; dùng groupingBy cho yêu cầu đó.

## 13. Đếm cha và con là hai phép khác nhau

Giả sử trong category "guide" có:

~~~text
Article A: tags = [java, stream]
Article B: tags = []
Article C: tags = [collector]
~~~

Số bài viết cha là **3**, số tag con là **3** (nếu tính cả lần xuất hiện), còn số tag phân biệt cũng là 3 trong ví dụ này.

Nếu thêm "java" vào Article C, số bài vẫn 3, số tag con thành 4, số tag phân biệt vẫn 3.

Cách đếm bài viết:

~~~java
Map<String, Long> articleCount = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.counting()));
~~~

Cách đếm tag:

~~~java
Map<String, Long> tagCount = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.counting())));
~~~

Đây là các đoạn minh họa. Trong **articleCount**, counting nhận **Article** nên đếm cha. Trong **tagCount**, counting nhận từng **String tag** sau flatMapping nên đếm con.

Khi trình bày dashboard hoặc báo cáo, đặt tên cụ thể như **articleCount**, **tagOccurrences**, **distinctTagCount**; nếu chỉ ghi "Count" dễ tạo nhầm lẫn giữa số bản ghi và số phần tử con.

## 14. FlatMapping có tạo một danh sách trung gian không?

Không nhất thiết. Nếu downstream là **summingLong**, **counting**, **toSet** hoặc **toCollection(TreeSet::new)**, mỗi phần tử U được chuyển trực tiếp tới accumulator tương ứng của downstream. Không có yêu cầu phải xây một **List<U> trung gian** chỉ để sau đó duyệt lại.

Ví dụ:

~~~java
Collectors.flatMapping(
        order -> order.lines().stream(),
        Collectors.summingLong(Line::amountCents))
~~~

Đây là biểu thức minh họa. Mỗi Line có thể được cộng vào tổng của nhóm. Lợi ích rõ ràng:

- Tránh tạo **Map<String,List<Line>>** lớn rồi mới duyệt từng List để tính tổng.
- Thể hiện ngay ý định của collector: làm phẳng các Line trong mỗi region và tính tổng.
- Downstream có thể là một Collector do ứng dụng tự định nghĩa khi cần kết quả nghiệp vụ chuyên biệt.

**Dù vậy, Stream con vẫn là Stream có vòng đời**, không phải một danh sách được chép. Không nên trả cùng một Stream đã bị tiêu thụ ở nhiều lần gọi mapper; hãy tạo Stream mới từ collection con mỗi lần mapper chạy.

## 15. Stream con, tài nguyên và vòng đời

Hợp đồng **Collectors.flatMapping** có xử lý đặc biệt với Stream do mapper trả: sau khi chuyển nội dung của Stream con vào downstream, Stream ấy được **đóng**. Điều này hữu ích khi mapper tạo một Stream có tài nguyên liên quan, nhưng **không có nghĩa mọi API tài nguyên ngoài đều được quản lý thay**.

Cân nhắc:

1. **Không tái sử dụng Stream con đã bị đóng/tiêu thụ.** Mỗi lần mapper được gọi phải trả Stream dùng được.
2. **Không giữ Stream con trong field để nhiều phần tử cha cùng trả nó.** Stream chỉ được tiêu thụ một lần; cấu trúc chia sẻ này dễ gây IllegalStateException.
3. **Nếu Stream con đại diện I/O**, xem xét lifecycle, checked exception và chính sách lỗi. Các API Java chuẩn nhận Function không khai báo checked exception tùy ý.
4. **Nếu mapper trả null Stream**, flatMapping xử lý như Stream rỗng; nhưng code rõ ràng hơn khi trả `Stream.empty()`.
5. **Không sử dụng Stream con để cập nhật chính collection nguồn đang duyệt**: tuân thủ non-interference của Stream.
6. **Không giữ reference đến một stream đã tiêu thụ để dùng lại sau collect**. Khi collect kết thúc, dữ liệu kết quả nằm trong downstream container, không phải Stream còn mở.

**Đừng nhầm việc đóng Stream với đóng mọi thứ mà các phần tử bên trong tham chiếu đến.** Stream.close() chạy các close handler đã đăng ký của chính Stream; tài nguyên khác do ứng dụng quản lý phải có hợp đồng riêng.

## 16. Đặc tính Collector, thứ tự và parallel stream

Với pipeline tuần tự trên List, việc `toList` gom tag theo encounter order thường dễ dự đoán. Khi chạy parallel, cần hiểu ranh giới bảo đảm:

- `groupingBy` là collector có thể tạo rồi kết hợp các map/container trung gian; không nên tự giả định số lần mapper được gọi hoặc thứ tự lịch thực thi cố định.
- `flatMapping` đưa từng Stream con vào downstream của nhóm. **Không dùng side effect trong mapper hoặc Stream con** để ghi audit bắt buộc.
- `toList` giữ thứ tự gặp nếu Stream có thứ tự và hợp đồng collect yêu cầu bảo toàn encounter order; nhưng `HashMap` mặc định không cam kết thứ tự lặp các **khóa nhóm**.
- `toSet` và `TreeSet` có quy tắc thứ tự khác nhau. Nếu một downstream collector **UNORDERED**, không được dựa vào thứ tự gặp như ý nghĩa nghiệp vụ.
- `groupingByConcurrent` là biến thể nhóm đồng thời nhưng có thể có đặc tính **UNORDERED**. Đừng thay thế `groupingBy` bằng `groupingByConcurrent` nếu thứ tự danh sách con quan trọng mà chưa kiểm tra contract.
- Tính thread-safe của collection kết quả **không tự sinh ra** chỉ bởi việc collect từ parallel stream.
- `parallel()` không luôn nhanh hơn: có chi phí chia/merge, và Stream con có thể nhỏ khiến overhead lớn.

**Khuyến nghị:** Khi kết quả cần thứ tự ổn định, hãy giữ nguồn có encounter order, chọn downstream có semantics rõ ràng và chỉ dùng parallel khi đã kiểm thử, đo lường với workload thật. Không dựa vào log của từng mapper làm bằng chứng về thứ tự dữ liệu cuối.

### 16.1. Đối tượng mutable và side effect

Nếu tag, Line hoặc Employee là object mutable, kết quả Set/List có thể chứa tham chiếu đến các object ấy. Tạo một List mới bằng Collector **không phải deep copy** các phần tử. Nếu một Comparator trong TreeSet phụ thuộc vào trường mutable rồi trường ấy thay đổi sau khi collect, quy tắc sắp xếp/tìm kiếm của TreeSet có thể không còn ổn định.

Tránh thay đổi List con ngay trong lúc `a.tags().stream()` đang duyệt. Điều này có thể gây ConcurrentModificationException hoặc vi phạm quy tắc non-interference.

## 17. Kết hợp sâu hơn: mapping, filtering, collectingAndThen

Một trong những giá trị của **Collector kết hợp** là có thể lắp nhiều adapter thành pipeline downstream:

~~~java
Map<String, List<String>> cleanTags = articles.stream()
        .collect(Collectors.groupingBy(
                Article::category,
                Collectors.flatMapping(
                        a -> a.tags().stream(),
                        Collectors.mapping(
                                String::toLowerCase,
                                Collectors.filtering(
                                        s -> !s.isBlank(),
                                        Collectors.toList())))));
~~~

Đây là đoạn minh họa, giả định tag không null. Từng String con được đổi sang chữ thường, lọc không blank và gom list theo category.

**Nhưng đừng ép mọi bước vào một collector quá sâu.** Một mapper rõ ràng cũng có thể làm việc tương đương:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty()),
        Collectors.toList())
~~~

Đây là đoạn minh họa có import Objects. Nó giữ các thao tác lọc/chuyển đổi tag ở gần nơi tạo Stream con; dễ đặt breakpoint và đọc hơn khi không cần tái sử dụng các collector adapter độc lập.

Có thể dùng **collectingAndThen(downstream, finisher)** nếu muốn chuyển kết quả mỗi nhóm thành một kiểu khác sau khi thu thập. Ví dụ tạo list unmodifiable từ một danh sách tạm:

~~~java
Collectors.flatMapping(
        a -> a.tags().stream(),
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf))
~~~

Đây là đoạn minh họa. **List.copyOf** không chấp nhận phần tử null, nên phải bảo đảm tag không null nếu dùng cách này. Bên cạnh đó, list kết quả không sửa được **về cấu trúc** nhưng không tạo bản sao sâu các object phần tử.

**Tiêu chí lựa chọn cách viết:** ưu tiên sự rõ ràng về loại phần tử trước/sau mỗi bước, xử lý null, thứ tự, khả năng sửa đổi và semantics nhóm hơn việc tạo biểu thức functional dài nhất.

## 18. Những lỗi phổ biến

| Lỗi/ngộ nhận | Hệ quả | Cách sửa |
| --- | --- | --- |
| Truyền List trực tiếp vào mapper của flatMapping | Sai kiểu; mapper phải trả Stream | Dùng `list.stream()` |
| Thay flatMapping bằng mapping khi cần danh sách phẳng | `List<List<U>>` không đúng mong muốn | Dùng flatMapping để đưa từng U vào downstream |
| FlatMap toàn bộ trước groupingBy khi cần giữ nhóm con rỗng | Nhóm có cha nhưng 0 con biến mất | groupingBy cha rồi downstream flatMapping |
| Cho rằng không có cha cũng tự tạo nhóm | Không xuất hiện khóa không có input | Bổ sung danh mục nhóm chuẩn riêng |
| Cho rằng counting luôn đếm số cha | Với flatMapping, counting đếm U con | Phân biệt đếm trước và sau làm phẳng |
| Dùng toSet rồi đòi giữ số lần trùng | Set loại trùng | Chọn toList hoặc counting |
| Dùng toSet rồi đòi thứ tự tag ổn định | Không cam kết thứ tự Set | Chọn LinkedHashSet/TreeSet đúng yêu cầu |
| TreeSet comparator chỉ so một thuộc tính không duy nhất | Mất phần tử được coi trùng | Bổ sung tie-breaker hoặc chọn List |
| Không kiểm tra tags list null | NPE từ `tags().stream()` | Validate hoặc trả Stream.empty có chính sách |
| Nhóm theo classifier trả null | `groupingBy` ném NPE | Xác thực hoặc chuẩn hóa khóa |
| Nghĩ flatMapping tự lọc null con | Downstream có thể nhận null | Filter/validate từng U |
| Tái sử dụng cùng Stream con | Stream đã tiêu thụ/đóng | Mỗi lần mapper tạo stream mới |
| Ghi side effect bắt buộc trong mapper | Parallel/optimization làm hành vi khó đoán | Tách side effect ra quy trình riêng |
| Dùng groupingByConcurrent rồi dựa vào encounter order | Khó giữ thứ tự có chủ đích | Chọn collector bảo toàn thứ tự phù hợp |
| Tưởng collect tạo deep copy | Các phần tử U có thể vẫn mutable | Chủ động clone/map nếu cần |
| Sử dụng List.copyOf trên kết quả có null | NPE khi finisher chạy | Loại/báo null theo hợp đồng |

## 19. Checklist khi viết flatMapping cho từng nhóm

1. **Đối tượng cha là gì (T)?** Ví dụ Article, Order, Employee.
2. **Khóa nhóm lấy từ đâu?** Phải xác định ở tầng cha hay tầng con; có thể null không?
3. **Mapper tạo Stream<U> như thế nào?** Không truyền thẳng List/Optional thay Stream.
4. **Một cha có thể phát 0 phần tử con không?** Có cần giữ nhóm rỗng không?
5. **Chọn downstream kết quả gì?** List, Set, TreeSet, counting, summingLong...
6. **Có phần tử con trùng hoặc null không?** Chọn chính sách dữ liệu.
7. **Có cần thứ tự ổn định không?** Xác định encounter order, mapFactory và Collection đích.
8. **Dữ liệu con có thể thiếu hoặc lỗi không?** Phân biệt empty hợp lệ với failure.
9. **Stream con có tài nguyên hoặc chỉ dùng một lần không?** Trả stream mới và quản lý lifecycle.
10. **Có side effect cần bảo đảm không?** Không giấu audit/cập nhật trạng thái trong collector.
11. **Có chạy parallel không?** Kiểm tra collector đặc tính, hiệu năng và ổn định đầu ra.
12. **Test cả nhóm có nhiều con, một con, 0 con và không có cha chưa?** Đây là bốn case căn bản.

## 20. Bài tập thực hành

### Bài 1: Mapping hay flatMapping?

Nguồn gồm hai Article cùng category "guide": bài A có tags ["java","stream"], bài B có tags ["collector"]. Hãy viết hai collector và dự đoán kiểu của từng kết quả:

~~~java
Collectors.mapping(Article::tags, Collectors.toList())
Collectors.flatMapping(a -> a.tags().stream(),
        Collectors.toList())
~~~

Đây là biểu thức minh họa. Đáp án kiểu: **List<List<String>>** so với **List<String>** trong mỗi nhóm.

### Bài 2: Giữ nhóm rỗng

Một category "faq" có một Article với `List.of()` tag. So sánh `groupingBy(Article::category, flatMapping(...))` với việc chuyển Article thành Stream<TagEntry> trước rồi `groupingBy(TagEntry::category)`. Vì sao faq chỉ xuất hiện ở cách thứ nhất?

### Bài 3: Số tag và số bài

Cho category "guide" có 3 Article, mỗi Article lần lượt 2, 0, 4 tag. Viết collector đếm số Article cha và collector đếm tổng 6 tag con. Dùng `counting()` đúng vị trí trong từng bài toán.

### Bài 4: Chọn loại downstream

Từ Stream<Article>, tạo:
- `Map<Category, List<Tag>>` giữ mọi lần xuất hiện.
- `Map<Category, LinkedHashSet<Tag>>` giữ tag duy nhất theo thứ tự đầu gặp.
- `Map<Category, TreeSet<Tag>>` sắp xếp tag theo thứ tự tự nhiên.

Giải thích loại Collection quyết định thế nào là phần tử trùng và thứ tự khi duyệt.

### Bài 5: Optional.stream()

Một Account có `Optional<String> referralCode`. Hãy nhóm theo team, thu tập mã giới thiệu. Các Account có Optional.empty() đóng góp bao nhiêu phần tử vào downstream? Nhóm có Account nhưng không có mã có xuất hiện không?

### Bài 6: Null-safe và dữ liệu hỏng

Một Employee có List<String> skills có thể null hoặc chứa phần tử null. Thiết kế hai phương án:
- Phương án cho phép absence: null list thành Stream.empty, lọc null skill.
- Phương án dữ liệu bắt buộc: báo lỗi Employee thiếu skills tại boundary.

Tại sao không được coi hai phương án có cùng ý nghĩa nghiệp vụ?

### Bài 7: Tổng hợp dòng tiền

Một Order có List<Line>, mỗi Line có `long amountCents`. Nhóm Order theo region, dùng flatMapping và summingLong để tính tổng. Thêm region có một Order nhưng 0 Line. Dự đoán giá trị tổng cho region đó.

### Bài 8: Quan sát parallel collector

Chạy cùng bộ dữ liệu tuần tự và song song, dùng TreeMap + downstream toList hoặc LinkedHashSet. Kiểm tra nội dung cuối theo hợp đồng thay vì dựa vào thứ tự log trong mapper. Giải thích vì sao không nên đếm số lần Supplier được tạo để suy ra số nhóm.

## 21. Ghi nhớ

**`Collectors.flatMapping(mapper, downstream)`** nhận từng phần tử cha **T**, dùng mapper tạo **Stream<U>**, rồi chuyển từng U cho downstream **trong nhóm tương ứng**. Nó rất hữu ích khi kết hợp với **groupingBy** hoặc **partitioningBy** để không phải giữ **List<List<U>>** hay xây thủ công các object trung gian chỉ để làm phẳng dữ liệu.

Đặt đúng thứ tự ý nghĩa: **groupingBy quyết định khóa nhóm từ cha; flatMapping quyết định những phần tử con đi vào nhóm; downstream quyết định kết quả của nhóm** (List, Set, tổng, đếm, v.v.). Một nhóm có cha nhưng 0 con vẫn có thể xuất hiện với accumulator rỗng; nhóm không có cha nào không được tạo tự động.

Cần kiểm tra kỹ **null ở cha, khóa, danh sách con và từng phần tử con**, vì flatMapping không phải công cụ chữa mọi loại null. Chọn downstream phù hợp với quy tắc trùng lặp, thứ tự và lỗi dữ liệu; tránh side effect và tái sử dụng Stream con.

Câu hỏi giúp chọn API: **“Tôi đang muốn làm phẳng dữ liệu của toàn luồng trước khi nhóm, hay muốn giữ nhóm cha và làm phẳng các phần tử con riêng trong từng nhóm?”** Nếu là trường hợp thứ hai, `Collectors.flatMapping()` chính là công cụ cần dùng.