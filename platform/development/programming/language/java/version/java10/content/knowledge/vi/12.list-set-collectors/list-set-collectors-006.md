# Phần tử trùng và lựa chọn đại diện trong `Collectors.toUnmodifiableSet()` (Java 10+)

## 1. Mục tiêu và kết luận quan trọng nhất

Khi gom một `Stream<T>` thành `Set<T>` không sửa được, Java cung cấp `Collectors.toUnmodifiableSet()` từ **Java 10**. Collector này **loại các phần tử trùng theo quan hệ bằng nhau của `Set`**. Nếu có nhiều đối tượng **bằng nhau nhưng là các instance khác nhau**, API nói rõ: **một đại diện bất kỳ trong số các đối tượng trùng sẽ được giữ lại** (*an arbitrary element of the duplicates is preserved*).

Vì vậy:

- **Số lượng phần tử** trong kết quả chỉ tính các nhóm phần tử phân biệt theo `equals`, không phải tổng số phần tử của stream.
- **Không được giả định “giữ phần tử đầu tiên” hay “giữ phần tử cuối cùng”** trong nhóm trùng, ngay cả khi stream đầu vào có encounter order.
- **Không được giả định thứ tự duyệt** của `Set` kết quả. `toUnmodifiableSet()` là một **unordered collector**.
- **Phần tử `null` không được phép**; collector ném `NullPointerException` nếu gặp null.
- **Kết quả không sửa được**; thêm/xóa phần tử qua `Set` kết quả bị từ chối bằng `UnsupportedOperationException`.

Đó là hợp đồng được quy định trong Java API hiện hành, không phải đặc điểm ngẫu nhiên của một bản JDK cụ thể. Bài này tập trung vào **duplicate và đại diện được giữ lại**, đồng thời giải thích các hệ quả cho thiết kế dữ liệu và kiểm thử.

## 2. Cú pháp, kiểu kết quả và ý nghĩa của Set

Đoạn sau minh họa cách dùng trong một phương thức:

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> input = List.of("A", "B", "A");
Set<String> result = input.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(result.size());        // 2
System.out.println(result.contains("A")); // true
System.out.println(result.contains("B")); // true
~~~

`Collectors.toUnmodifiableSet()` có chữ ký tổng quát dạng:

~~~java
static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()
~~~

*Chữ ký trên là minh họa API thư viện, không phải phương thức bạn cần tự khai báo.*

`Stream.collect` sử dụng collector này để gom các phần tử và trả về một `Set<T>` không sửa được. Nếu viết `var result = input.stream().collect(Collectors.toUnmodifiableSet());`, kiểu tĩnh được suy luận của `result` vẫn là `Set<String>` trong ví dụ.

**Set không phải List.** `List` có thể chứa nhiều phần tử bằng nhau ở các vị trí khác nhau, còn `Set` chỉ giữ một phần tử đại diện cho mỗi nhóm bằng nhau. Sự khác biệt này là lý do `result.size()` bằng 2 dù `input.size()` bằng 3.

Không in `result` để suy luận thứ tự `[A, B]` hay `[B, A]`: thứ tự duyệt của set trả về **không được cam kết**.

## 3. Thế nào là “trùng”? Vai trò của `equals` và `hashCode`

Hai phần tử được coi là trùng trong `Set` theo **ngữ nghĩa bằng nhau**, thông thường dựa trên `equals(Object)`, chứ không đơn thuần dựa vào địa chỉ đối tượng.

Với `String`:

~~~java
var input = java.util.List.of(
        new String("Java"),
        new String("Java"),
        "Stream");

var values = input.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

System.out.println(values.size());         // 2
System.out.println(values.contains("Java")); // true
~~~

Hai đối tượng tạo từ `new String("Java")` là hai instance khác nhau nhưng bằng nhau về nội dung theo `String.equals`. Kết quả chỉ giữ một đại diện `"Java"`.

Với lớp tự định nghĩa, cần tuân thủ hợp đồng `equals` và `hashCode`. Nếu override `equals` để hai đối tượng được coi là bằng nhau, bạn cũng phải override `hashCode` sao cho **đối tượng bằng nhau có hash code bằng nhau**. Nếu không, tập hợp sử dụng hashing có thể hoạt động không như mong đợi.

**Phân biệt trùng và hash collision:** hai đối tượng khác nhau có cùng `hashCode()` **không tự trở thành phần tử trùng**. `hashCode` được dùng để tổ chức tìm kiếm, nhưng ý nghĩa bằng nhau vẫn phụ thuộc hợp đồng `equals`.

## 4. Ví dụ then chốt: hai đối tượng bằng nhau nhưng khác dữ liệu phụ

Để thấy việc lựa chọn đại diện thực sự quan trọng, ta tạo một lớp `Tag` với hai trường:

- `code` là **khóa định danh dùng trong `equals` và `hashCode`**.
- `origin` chỉ cho biết bản ghi đến từ nguồn nào và **không tham gia xác định bằng nhau**.

~~~java
static final class Tag {
    final String code;
    final String origin;

    Tag(String code, String origin) {
        this.code = code;
        this.origin = origin;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Tag
                && code.equals(((Tag) other).code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }

    @Override
    public String toString() {
        return code + "-" + origin;
    }
}
~~~

Đây là **lớp lồng tĩnh minh họa** đặt trong một lớp Java; không chạy độc lập. `instanceof Tag` và phép ép kiểu trong phương thức `equals` sử dụng cú pháp hoạt động từ Java 10.

Xét ba phần tử:

~~~java
var input = java.util.List.of(
        new Tag("A", "first"),
        new Tag("A", "later"),
        new Tag("B", "only"));

var result = input.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

Hai đối tượng `Tag("A", "first")` và `Tag("A", "later")` **khác tham chiếu**, nhưng `equals` trả về true vì cùng `code = "A"`; chúng thuộc một nhóm trùng. `Tag("B", "only")` thuộc nhóm còn lại.

Kết quả phải thỏa mãn:

~~~java
System.out.println(result.size()); // 2

System.out.println(
        result.contains(new Tag("A", "other"))); // true
~~~

Điều gì **không được** suy luận?

~~~java
// KHÔNG có bảo đảm:
// result phải chứa đúng đối tượng input.get(0) (first)
// result phải chứa đúng đối tượng input.get(1) (later)
~~~

Nếu cần kiểm tra nhóm `"A"` có đúng một đại diện:

~~~java
long countA = result.stream()
        .filter(tag -> tag.code.equals("A"))
        .count();

System.out.println(countA); // 1
~~~

Nếu muốn xem `origin` của đại diện được chọn trong lúc tìm hiểu, bạn có thể đọc nó, nhưng **đừng ghi một giá trị cụ thể như "first" vào output mong đợi của bài test**. Một lần chạy có thể chọn một đại diện nhất định; điều đó không tạo ra cam kết API để sử dụng trong sản phẩm.

## 5. “Một đại diện bất kỳ” không đồng nghĩa “chọn ngẫu nhiên”

Tài liệu API dùng từ **arbitrary**, nghĩa là **không xác định bởi hợp đồng** đại diện nào sẽ thắng. Nó **không** nói collector sử dụng bộ sinh số ngẫu nhiên, và **không** hứa rằng các lần chạy liên tiếp phải chọn khác nhau.

Vì vậy, cả hai kiểu diễn giải sau đều sai:

- “Tôi chạy 100 lần thấy `first` được giữ, vậy Java luôn lấy phần tử đầu.”
- “Vì arbitrary nên mỗi lần chạy sẽ chọn một phần tử ngẫu nhiên khác nhau.”

Việc quan sát cùng một lựa chọn trong một phiên bản JDK, với một kích thước tập nhỏ và một cách xử lý stream cụ thể, **không phải bằng chứng về hành vi ổn định theo hợp đồng**. Một thay đổi về dữ liệu, số phần tử, runtime hoặc cách thu gom có thể làm kết quả khác.

**Cách sử dụng đúng:** thiết kế nghiệp vụ không phụ thuộc vào `origin` hay identity của phần tử đại diện nếu những thuộc tính đó không tham gia quan hệ bằng nhau. Nếu thông tin `origin` cần được ưu tiên theo quy tắc (chẳng hạn “lấy bản đầu tiên”, “lấy bản mới nhất”), hãy áp dụng quy tắc ấy trước khi xây dựng `Set` kết quả.

## 6. Tại sao encounter order không đảm bảo “first wins”?

Một `List` có thứ tự duyệt xác định:

~~~java
var tags = java.util.List.of(
        new Tag("A", "first"),
        new Tag("A", "later"));
~~~

`tags.stream()` là stream có thứ tự encounter order theo danh sách, nhưng `Collectors.toUnmodifiableSet()` được đặc tả là **unordered collector**. Nó không phải một collector lựa chọn đại diện theo vị trí.

~~~java
var result = tags.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

Ngay cả khi dùng stream **tuần tự**, việc quan sát kết quả “first” ở lần chạy nào đó không đủ để xây dựng quy tắc nghiệp vụ. Khi dùng `parallelStream()` hoặc `stream().parallel()`, các phần tử có thể được tích lũy vào nhiều container trung gian rồi kết hợp. Càng không nên dựa vào lựa chọn đại diện cụ thể.

Có thể kiểm tra đặc tính `UNORDERED` của collector:

~~~java
var collector = java.util.stream.Collectors.<Tag>toUnmodifiableSet();

boolean unordered = collector.characteristics().contains(
        java.util.stream.Collector.Characteristics.UNORDERED);

System.out.println(unordered); // true
~~~

**Phân biệt hai khái niệm:**

1. **Encounter order của stream đầu vào:** nguồn `List` có thứ tự rõ ràng.
2. **Hợp đồng của collector đầu ra:** `toUnmodifiableSet` không cam kết giữ thứ tự hoặc chọn phần tử trùng theo thứ tự đầu vào.

Muốn “first wins” có nghĩa nghiệp vụ, phải dùng giải pháp nêu rõ chính sách gộp; việc chỉ thêm `sequential()` **không thay thế hợp đồng lựa chọn đại diện**.

## 7. Chương trình Java hoàn chỉnh: kiểm tra không phụ thuộc đại diện cụ thể

Lưu tệp **`UnmodifiableSetDuplicatesDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnmodifiableSetDuplicatesDemo {

    static final class Tag {
        final String code;
        final String origin;

        Tag(String code, String origin) {
            this.code = code;
            this.origin = origin;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Tag
                    && code.equals(((Tag) other).code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }

        @Override
        public String toString() {
            return code + "-" + origin;
        }
    }

    public static void main(String[] args) {
        var input = List.of(
                new Tag("A", "first"),
                new Tag("A", "later"),
                new Tag("B", "only"));

        Set<Tag> result = input.stream()
                .collect(Collectors.toUnmodifiableSet());

        // Không kiểm tra thứ tự hoặc đại diện "first/later".
        System.out.println("size=" + result.size());
        System.out.println("Acount=" + result.stream()
                .filter(tag -> tag.code.equals("A")).count());

        System.out.println("containsA="
                + result.contains(new Tag("A", "other")));

        var representative = result.stream()
                .filter(tag -> tag.code.equals("A"))
                .findAny()
                .orElseThrow();

        System.out.println("candidateFromInput="
                + (representative == input.get(0)
                || representative == input.get(1)));

        var collector = Collectors.<Tag>toUnmodifiableSet();
        System.out.println("unordered=" + collector.characteristics()
                .contains(Collector.Characteristics.UNORDERED));

        try {
            result.add(new Tag("C", "new"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("add=blocked");
        }

        try {
            Stream.of("A", null).collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException ex) {
            System.out.println("null=blocked");
        }

        // Khi chính sách bắt buộc "first wins", chọn trước khi tạo Set.
        Map<String, Tag> firstByCode = new LinkedHashMap<>();
        for (var tag : input) {
            firstByCode.putIfAbsent(tag.code, tag);
        }

        Set<Tag> chosen = Set.copyOf(firstByCode.values());
        System.out.println("firstByCodeA=" + firstByCode.get("A").origin);
        System.out.println("chosenSize=" + chosen.size());
        System.out.println("chosenContainsFirstA="
                + chosen.contains(input.get(0)));
    }
}
~~~

Mã dùng các API từ Java 10 trở về trước và cú pháp `var` từ Java 10; có thể biên dịch, chạy bằng **JDK 17+**:

~~~bash
javac UnmodifiableSetDuplicatesDemo.java
java UnmodifiableSetDuplicatesDemo
~~~

**`stdout` đã được kiểm tra trên JDK 24:**

~~~text
size=2
Acount=1
containsA=true
candidateFromInput=true
unordered=true
add=blocked
null=blocked
firstByCodeA=first
chosenSize=2
chosenContainsFirstA=true
~~~

Vì sao output này đáng tin?

- `size=2` và `Acount=1` kiểm tra số nhóm phần tử bằng nhau, **không kiểm tra đại diện nào thắng**.
- `containsA=true` kiểm tra bằng nhau theo `Tag.equals`; một đối tượng `Tag("A", "other")` vẫn được coi là phần tử có mặt.
- `candidateFromInput=true` cho biết đại diện nhóm A là một trong hai đối tượng gốc, nhưng **không khẳng định là đối tượng thứ nhất hay thứ hai**.
- `unordered=true` xác nhận đặc tính của collector.
- `add=blocked` và `null=blocked` kiểm tra hai quy tắc khác của collector.
- `firstByCodeA=first` là kết quả của **mã lựa chọn chủ động bằng `putIfAbsent`**, không phải cam kết của `toUnmodifiableSet()`.

Lưu ý: `chosen.contains(input.get(0))` xác nhận phần tử có **giá trị bằng nhau** theo `equals`; phương thức `contains` **không** tự kiểm tra có phải cùng đối tượng theo `==`. Trong ví dụ này `firstByCode` còn giúp ta biết chính xác đối tượng được chủ động giữ lại.

## 8. Nếu cần đại diện xác định, chủ động đặt quy tắc gộp

Giả sử một stream có nhiều bản ghi cùng `code` nhưng khác `origin`. Nếu mục tiêu nghiệp vụ là “giữ bản xuất hiện đầu tiên theo thứ tự đầu vào” trong một **List được duyệt tuần tự**, ta nên viết quy tắc đó rõ ràng:

~~~java
var input = java.util.List.of(
        new Tag("A", "first"),
        new Tag("A", "later"),
        new Tag("B", "only"));

var chosenByCode = new java.util.LinkedHashMap<String, Tag>();

for (var tag : input) {
    chosenByCode.putIfAbsent(tag.code, tag);
}

System.out.println(chosenByCode.get("A").origin); // first
~~~

Với `putIfAbsent` trên map mutable và nguồn `input` được duyệt theo thứ tự, bản đầu tiên của mỗi `code` đã có giá trị sẽ được giữ, bản sau cùng khóa không ghi đè. Đây là **chính sách do ứng dụng tự định nghĩa**, không phụ thuộc collector bỏ trùng theo đại diện tùy ý.

Sau khi chọn xong, có thể công bố dưới dạng set không sửa được:

~~~java
var chosenSet = java.util.Set.copyOf(chosenByCode.values());
~~~

Ví dụ `Tag.equals` dùng đúng `code`, nên `chosenByCode.values()` chỉ còn **một đối tượng cho mỗi nhóm bằng nhau**. `Set.copyOf` không còn phải giải quyết nhiều ứng viên trùng cho cùng một code; các đại diện đã được mã ứng dụng chọn.

**Đừng lấy `chosenSet.iterator().next()` để suy luận thứ tự**: `Set.copyOf` không bảo đảm thứ tự duyệt. Nếu còn cần thứ tự theo lần xuất hiện đầu tiên, hãy lưu một **`List` không sửa được**:

~~~java
var orderedChosen = java.util.List.copyOf(chosenByCode.values());
// Danh sách giữ thứ tự duyệt của LinkedHashMap.values().
~~~

Nếu muốn quy tắc “last wins”:

~~~java
var lastByCode = new java.util.LinkedHashMap<String, Tag>();

for (var tag : input) {
    lastByCode.put(tag.code, tag);
}

System.out.println(lastByCode.get("A").origin); // later
~~~

`put` ghi đè giá trị của khóa đã tồn tại. Chính sách “last wins” lúc này là do thuật toán lựa chọn, không phải do `toUnmodifiableSet`.

### Dùng collector khác khi muốn chính sách gộp

Có thể dùng `Collectors.toMap(keyMapper, valueMapper, mergeFunction, mapSupplier)` để mô tả cách giải quyết các khóa trùng. Ví dụ minh họa bên trong phương thức:

~~~java
var firstByCode = input.stream().collect(
        java.util.stream.Collectors.toMap(
                tag -> tag.code,
                java.util.function.Function.identity(),
                (first, later) -> first,
                java.util.LinkedHashMap::new));
~~~

Đoạn trên dùng **stream tuần tự có encounter order từ List**; merge function chủ động ưu tiên giá trị đã tích lũy khi khóa trùng. Để dễ đọc và tránh các giả định khi chuyển sang xử lý song song, vòng `for` + `putIfAbsent` thường rõ ràng nhất đối với chính sách “first wins”.

**Phân biệt** `toUnmodifiableMap`: overload không có merge function từ chối khóa trùng bằng ngoại lệ; nó không phải phiên bản dùng để tự động áp đặt một chính sách “first wins”. Muốn gộp khóa trùng, phải chọn overload có hàm merge hoặc thuật toán khác diễn đạt rõ ý định.

## 9. So sánh `toUnmodifiableSet`, `toSet`, `Set.copyOf` và `Set.of`

| API | Đầu vào | Duplicate | Có thể sửa kết quả? | Ghi chú |
| --- | --- | --- | --- | --- |
| `stream.collect(Collectors.toUnmodifiableSet())` | `Stream<T>` | Giữ **một đại diện tùy ý** của nhóm bằng nhau | Không | Unordered collector; Java 10+; không nhận null |
| `stream.collect(Collectors.toSet())` | `Stream<T>` | Set loại trùng theo bằng nhau | **Không có cam kết** về mutability | Cũng là unordered collector; không dựa vào việc hiện trả về HashSet |
| `Set.copyOf(collection)` | `Collection<? extends T>` | Giữ một đại diện tùy ý của nhóm bằng nhau | Không | Java 10+; không nhận null |
| `Set.of(a, b, ...)` | Các phần tử trực tiếp | **Ném `IllegalArgumentException` nếu trùng** | Không | Java 9+; không nhận null |

Hai điểm đặc biệt quan trọng:

1. `Set.of(...)` **không** tự loại trùng bằng cách chọn đại diện; nó từ chối lời gọi tạo tập nếu đối số có duplicate.
2. `Set.copyOf(...)` và `Collectors.toUnmodifiableSet()` có hành vi **giữ một phần tử đại diện không xác định** cho nhóm trùng theo hợp đồng, thay vì ném lỗi duplicate.

`Collectors.toSet()` có thể trả về một `HashSet` có thể sửa ở một cài đặt hiện tại, nhưng tài liệu không bảo đảm kiểu cụ thể hoặc khả năng sửa của kết quả. Nếu ứng dụng cần set mutable do chính mình kiểm soát, hãy dùng `Collectors.toCollection(HashSet::new)` (và chấp nhận chính sách gộp phần tử của `HashSet`), hoặc tạo một `HashSet` tường minh.

Với dữ liệu **không có duplicate** và chỉ cần tập không sửa được, `toUnmodifiableSet()` là lựa chọn rất phù hợp: gọn và biểu lộ đúng ý định.

## 10. Những giả định không an toàn trong kiểm thử

### Sai: kiểm tra phần tử đứng đầu iterator

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

// Không nên viết:
// assert result.iterator().next().equals("A");
~~~

Thứ tự duyệt `Set` kết quả không được cam kết. Một kiểm thử kiểu đó có thể “đúng tình cờ” trên JDK đang chạy nhưng sai với môi trường khác.

### Sai: kiểm tra đại diện có `origin = "first"`

~~~java
var result = input.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());

// Không nên đòi hỏi:
// assert result.stream().filter(t -> t.code.equals("A"))
//        .findAny().orElseThrow().origin.equals("first");
~~~

`origin` không được dùng để xác định trùng, nên API không có lý do phải ưu tiên một giá trị `origin` cụ thể.

### Đúng: kiểm tra thuộc tính hợp đồng

~~~java
// Giả sử result chứa các Tag có code A, A, B.
assert result.size() == 2;
assert result.contains(new Tag("A", "anything"));
assert result.contains(new Tag("B", "anything"));
~~~

Kiểm thử có thể bổ sung xác nhận `UnsupportedOperationException` khi cố thêm phần tử và `NullPointerException` khi stream chứa `null`.

Nếu nghiệp vụ đòi “first wins”, hãy **kiểm thử thuật toán chọn đại diện do bạn tự viết**, không bắt `toUnmodifiableSet` thực hiện một hợp đồng mà nó không hứa.

## 11. Các lỗi thường gặp

### Lỗi 1: nhầm `==` với `equals`

~~~java
var a = new String("A");
var b = new String("A");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

`Set` coi chúng là cùng một giá trị theo `equals`, nên sẽ chỉ chứa một đại diện. Nếu thực sự cần phân biệt các instance dù nội dung bằng nhau, một `Set` dựa trên `equals` không phải mô hình dữ liệu đáp ứng yêu cầu; hãy dùng cấu trúc giữ nhiều mục như `List` hoặc thiết kế một khóa có danh tính rõ ràng.

### Lỗi 2: chỉ override `equals` mà không override `hashCode`

Một lớp tùy chỉnh phải duy trì hợp đồng: **hai đối tượng bằng nhau theo `equals` phải có cùng `hashCode`**. Nếu phá hợp đồng, đừng mong collector gom trùng chính xác. Với mô hình `Tag` đã nêu, cả hai đều sử dụng `code` nên phù hợp.

### Lỗi 3: sửa khóa thuộc tính dùng trong `equals`/`hashCode` sau khi thu thập

Nếu một phần tử trong `Set` là đối tượng mutable và bị sửa thuộc tính ảnh hưởng `equals` hoặc `hashCode`, hành vi của set có thể trở nên không được xác định hoặc tra cứu thất bại. Việc `Set` không sửa được chỉ ngăn thay đổi **cấu trúc tập hợp**, không khóa trạng thái đối tượng được giữ bên trong.

Nên dùng phần tử bất biến đối với thuộc tính định danh. Trong ví dụ `Tag`, `code` là `final String`, giúp tránh thay đổi bất hợp lệ theo đường thông thường.

### Lỗi 4: cho rằng `null` được bỏ qua

~~~java
// Lời gọi này ném NullPointerException:
java.util.stream.Stream.of("A", null)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

`toUnmodifiableSet` từ chối null, không tự lọc. Nếu đặc tả ứng dụng cho phép bỏ phần tử null, hãy lọc **trước khi collect**:

~~~java
var result = java.util.stream.Stream.of("A", null, "B")
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

Nếu `null` là dấu hiệu lỗi dữ liệu, tốt hơn nên báo lỗi rõ thay vì im lặng lọc.

### Lỗi 5: nhầm unmodifiable với deep immutable

Sau khi thu thập, `set.add(x)` bị từ chối. Nhưng một đối tượng trong set vẫn có thể thay đổi trường `origin` hoặc các trường khác nếu lớp thiết kế cho phép. `toUnmodifiableSet` **không sao chép sâu** đối tượng đầu vào. Hãy kiểm soát tính bất biến của phần tử khi cần một snapshot dữ liệu thật sự ổn định.

## 12. Các câu hỏi tự kiểm tra

**Câu 1.** Dùng `Stream.of("A","B","A").collect(Collectors.toUnmodifiableSet())`, kích thước kết quả là bao nhiêu? Có chắc iteration ra `A` trước `B` không?

**Đáp án:** Kích thước bằng **2**. **Không** có bảo đảm thứ tự duyệt.

**Câu 2.** Hai `Tag` có cùng `code` nhưng `origin` khác nhau sẽ ra sao?

**Đáp án:** Chỉ có một phần tử đại diện cho `code` đó. Đại diện có thể là một trong những đối tượng trùng, **không được cam kết là `first` hay `later`**.

**Câu 3.** Vì sao chạy stream tuần tự nhiều lần đều thấy đại diện `first` cũng không được viết business rule “first wins”?

**Đáp án:** `toUnmodifiableSet` là unordered collector và tài liệu chỉ bảo đảm **một đại diện tùy ý**. Kết quả quan sát trên một JDK là chi tiết triển khai, không phải hợp đồng.

**Câu 4.** Nếu muốn giữ bản đầu tiên của mỗi `code` từ một `List` đã có thứ tự, làm gì?

**Đáp án:** Duyệt danh sách tuần tự và dùng `LinkedHashMap.putIfAbsent(code, tag)`, sau đó công bố các phần tử được chọn thành collection không sửa được. Chính sách được xác định ở bước gộp, không dựa vào `toUnmodifiableSet`.

**Câu 5.** Phân biệt `Set.of("A","A")` và `Stream.of("A","A").collect(Collectors.toUnmodifiableSet())`.

**Đáp án:** `Set.of` ném `IllegalArgumentException` do duplicate; collector hợp lệ và cho set có **1** phần tử.

**Câu 6.** Có thể làm `result.add(new Tag("C","new"))` trên kết quả collector không?

**Đáp án:** Không. `Set` trả về không sửa được, thao tác bị từ chối bằng `UnsupportedOperationException`.

## 13. Tóm tắt

- `Collectors.toUnmodifiableSet()` được bổ sung **Java 10**, vẫn áp dụng hiện nay.
- **Phần tử trùng theo `equals`** chỉ giữ **một đại diện bất kỳ**; các instance bằng nhau nhưng có trường phụ khác nhau không có chính sách ưu tiên “first” hoặc “last”.
- **Không dựa vào encounter order** để đoán đại diện hoặc thứ tự duyệt, vì đây là **unordered collector**.
- **Luôn đảm bảo `equals/hashCode` nhất quán**, tránh sửa thuộc tính tham gia hai phương thức này sau khi đối tượng đã ở trong set.
- **Kết quả unmodifiable**, **không chấp nhận `null`**, nhưng **không tự làm các phần tử mutable trở thành bất biến sâu**.
- Nếu cần **đại diện xác định**, dùng chính sách gộp chủ động (`putIfAbsent`, `put`, hoặc collector có merge function) rồi mới công bố collection kết quả.

### Tài liệu chính thức

- [Java SE 26 — `Collectors.toUnmodifiableSet()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()): quy tắc duplicate, đại diện arbitrary, null và `UNORDERED`; `Since: 10`.
- [Java SE 26 — `Set`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html): ngữ nghĩa phần tử trùng và lưu ý phần tử mutable.
- [Oracle Java — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html): so sánh các collection không sửa được.
