# Lựa chọn Stream hoặc vòng lặp theo độ rõ ràng trong Java

## 1. Câu hỏi đúng không phải “Stream hay vòng lặp nhanh hơn?”

Java 8 giới thiệu **Stream API** để mô tả việc xử lý một dãy phần tử dưới dạng pipeline: lấy nguồn, lọc/biến đổi rồi thực hiện một phép kết thúc. Trước đó và cả hiện nay, các vòng lặp `for`, enhanced `for` và `while` vẫn là cấu trúc cơ bản, hữu ích của Java. Hai cách **không loại trừ nhau** và không có quy tắc “mã Java hiện đại thì bắt buộc phải dùng Stream”.

Ví dụ cùng một yêu cầu — chuẩn hóa và chọn tên hợp lệ — có thể viết dưới hai dạng:

~~~java
// Mảnh mã minh họa, cần nguồn names kiểu List<String>.
List<String> result = names.stream()
        .filter(name -> name != null && !name.isBlank())
        .map(String::trim)
        .toList();
~~~

Hoặc:

~~~java
// Mảnh mã minh họa, cần imports List và ArrayList.
List<String> result = new ArrayList<>();
for (String name : names) {
    if (name == null || name.isBlank()) {
        continue;
    }
    result.add(name.trim());
}
~~~

Cả hai đều có thể diễn đạt đúng yêu cầu. Câu hỏi quan trọng là **người đọc có hiểu ngay trình tự xử lý, trạng thái, điều kiện dừng, lỗi và kết quả không?** Khả năng mở rộng, kiểm thử và hiệu năng cũng quan trọng, nhưng đừng hy sinh tính đúng đắn hoặc khả năng đọc chỉ vì thích một cú pháp.

**Nguyên tắc làm việc:** ưu tiên **Stream** khi bài toán là một pipeline xử lý tập dữ liệu với các phép *lọc — ánh xạ — gom/giảm* rõ ràng; ưu tiên **vòng lặp** khi bài toán đòi hỏi các bước có trạng thái, điều khiển luồng phức tạp, dừng/thoát nhiều tầng, xử lý ngoại lệ theo từng phần tử hoặc side effect tuần tự rõ ràng. Khi hai dạng đều dễ hiểu, chọn theo quy ước nhóm và kiểm thử thực tế.

Các nội dung dưới đây dùng Java 17+ cho các chương trình chạy đầy đủ. `Stream` là API từ Java 8; `List.of` có từ Java 9, `String.isBlank` từ Java 11, `Stream.toList()` từ Java 16 và `record` được chuẩn hóa từ Java 16. Các khác biệt phiên bản đều được ghi rõ để không nhầm API mới là Java 8 nguyên bản.

## 2. Mô hình tư duy: pipeline khai báo và thủ tục điều khiển

### Stream mô tả **điều gì** xảy ra với dữ liệu

Một pipeline có dạng:

~~~text
Nguồn           Trung gian                                  Kết thúc
collection.stream() -> filter(...) -> map(...) -> distinct() -> toList()
~~~

Những thao tác trung gian như `filter`, `map`, `flatMap`, `sorted` và `distinct` thường **lazy**: chúng ghi nhận công việc cần làm; khi terminal như `toList`, `collect`, `count`, `findFirst` hoặc `anyMatch` được gọi, pipeline mới được đánh giá theo quy tắc của Stream.

Một pipeline tốt thường đọc gần với câu yêu cầu nghiệp vụ:

> Lấy các hóa đơn, chỉ giữ hóa đơn đã thanh toán, chuyển thành số tiền, rồi tính tổng.

~~~java
// Mảnh mã minh họa, Invoice có paid() và amount() thích hợp:
long total = invoices.stream()
        .filter(Invoice::paid)
        .mapToLong(Invoice::amount)
        .sum();
~~~

Trong code phù hợp, người đọc thấy rõ **nguồn**, **điều kiện**, **ánh xạ**, **terminal** và kiểu số của tổng.

### Vòng lặp mô tả **trình tự thực hiện**

Một vòng lặp thể hiện trực tiếp thứ tự, nhánh, cập nhật trạng thái và điểm dừng:

~~~java
// Mảnh mã minh họa:
long total = 0;
for (Invoice invoice : invoices) {
    if (!invoice.paid()) {
        continue;
    }
    total += invoice.amount();
}
~~~

Điểm mạnh của vòng lặp là mọi thay đổi của `total`, điều kiện `continue` và các lệnh khác đều xuất hiện như những bước rõ ràng trong một block. Một vòng lặp ngắn, không chứa nhiều nhánh, có thể **dễ đọc ngang hoặc hơn** một pipeline Stream.

**Kết luận:** không đánh giá code chỉ bằng số dòng. Một pipeline 5 lời gọi có thể dễ đọc hơn vòng lặp 12 dòng; cũng có pipeline 12 lời gọi lồng lambda và Optional phức tạp còn khó hiểu hơn vòng lặp 15 dòng.

## 3. Những trường hợp Stream thường diễn đạt rõ hơn

Stream thường phù hợp khi dữ liệu đi qua các phép biến đổi **độc lập, dễ đặt tên** và kết quả là một giá trị hoặc một tập mới:

- **Lọc**: `filter(predicate)`.
- **Biến đổi**: `map(function)` hoặc primitive mapping như `mapToInt`.
- **Trải phẳng** dữ liệu lồng nhau: `flatMap`.
- **Loại trùng**: `distinct`.
- **Sắp xếp**: `sorted(comparator)`.
- **Phân nhóm/tổng hợp**: `collect(Collectors.groupingBy(...))`, `summingInt`, `counting`, `joining`.
- **Tìm phần tử/thử điều kiện**: `findFirst`, `anyMatch`, `allMatch`, `noneMatch`.
- **Đầu ra rõ ràng**: `toList` hoặc một collector phù hợp.

Mỗi bước có thể tách thành helper method hoặc method reference có tên cụ thể, giúp người đọc nhận diện ý nghĩa mà không cần giải mã lambda dài.

Ví dụ:

~~~java
List<String> labels = products.stream()
        .filter(Product::isAvailable)
        .map(Product::displayName)
        .filter(Objects::nonNull)
        .sorted()
        .toList();
~~~

Đây là mảnh mã minh họa, giả sử `Product` có hai method nêu trên và đã import `Objects`. Nó biểu đạt tập hợp kết quả: **tên hiển thị đã sắp xếp của sản phẩm khả dụng**.

### Khi nào pipeline bắt đầu khó đọc?

Cẩn thận nếu bạn phải:

- Đặt nhiều phép biến đổi có lambda dài hàng chục dòng.
- Dùng `AtomicInteger` hoặc mảng một phần tử chỉ để có biến mutable ở bên ngoài lambda.
- Dùng `peek` để cập nhật database, gửi email, ghi audit bắt buộc hoặc tạo side effect nghiệp vụ.
- Lồng `Optional`, nhiều `flatMap` và `collect` khiến kiểu dữ liệu ở từng bước khó theo dõi.
- Dùng `reduce` với accumulator thay đổi danh sách mutable hoặc phụ thuộc thứ tự trong khi kết quả có thể sai khi parallel.
- Cần `break`, `continue` theo nhiều mức, `return` khỏi method chứa vòng lặp hay xử lý lỗi khác nhau cho từng phần tử.

Đừng cố đưa mọi thuật toán vào Stream. **Một API hiện đại không đồng nghĩa một cú pháp luôn là tốt nhất**.

## 4. Khi nào vòng lặp thường rõ hơn?

### 4.1. Trạng thái giữa các phần tử

Ví dụ cần chia các giá trị thành nhóm sao cho tổng mỗi nhóm không vượt một giới hạn. Việc xử lý giá trị hiện tại phụ thuộc **tổng đang tích lũy của nhóm trước**; đây là trạng thái tuyến tính:

~~~text
số hiện tại -> đủ chỗ trong nhóm? -> thêm vào
                            không -> chốt nhóm cũ -> mở nhóm mới
~~~

Một vòng lặp ghi rõ ranh giới nhóm và thời điểm reset trạng thái. Nếu biến việc này thành một `forEach` với nhiều biến mutable được capture qua object bao, bạn không làm thuật toán đơn giản hơn mà chỉ che đi state transition.

### 4.2. Dừng ở một điều kiện và trả về sớm

Nếu đang duyệt các bước một quy trình và phải **return cả method** khi nhận lỗi đầu tiên, vòng lặp biểu diễn `return` rất trực tiếp:

~~~java
// Mảnh mã minh họa, validate(...) trả Optional<Problem>.
for (Item item : items) {
    Optional<Problem> problem = validate(item);
    if (problem.isPresent()) {
        return problem;
    }
}
return Optional.empty();
~~~

Stream cũng có terminal `findFirst`, `anyMatch` và có thể short-circuit. Nó có thể **rõ hơn** vòng lặp khi điều kiện rất đơn giản. Nhưng nếu nhiều loại lỗi cần xử lý ngay, logging và rollback khác nhau, vòng lặp thường biểu đạt tốt hơn.

### 4.3. Ngoại lệ kiểm tra và tài nguyên theo từng phần tử

Một đoạn nhập dữ liệu có thể cần: thử parse, ghi danh sách lỗi, báo vị trí dòng, bỏ qua một lỗi được phép, dừng với lỗi nghiêm trọng. Với một vòng lặp, `try/catch`, `continue`, `break` và `return` đều là control flow thông thường.

Trong Stream, `Function.apply` và `Predicate.test` của các interface chuẩn không khai báo checked exception tùy ý. Có thể dùng helper trả `Result`/record kết quả từng phần tử, nhưng điều đó **chỉ nên làm nếu kết quả trung gian có giá trị thiết kế thật sự**, không phải để giữ bằng được cú pháp Stream.

### 4.4. Nhiều side effects bắt buộc có thứ tự

Nếu mỗi phần tử phải gọi một API bên ngoài theo thứ tự, xử lý retry, áp backoff, cập nhật checkpoint và rollback, vòng lặp tuần tự thường phản ánh đúng mô hình vận hành. Stream `forEach` có thể dùng cho một side effect đơn giản, nhưng không phải lựa chọn mặc định tốt cho một workflow I/O nhiều nhánh.

## 5. Ví dụ chạy đầy đủ 1: hai cách có cùng kết quả

Tạo tệp **StreamOrLoopDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class StreamOrLoopDemo {

    static List<String> withLoop(List<String> source) {
        List<String> result = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();

        for (String raw : source) {
            String name = raw.trim();
            if (name.isBlank()) {
                continue;
            }
            String normalized = name.toUpperCase(Locale.ROOT);
            if (seen.add(normalized)) {
                result.add(normalized);
            }
        }
        return result;
    }

    static List<String> withStream(List<String> source) {
        return source.stream()
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .distinct()
                .toList();
    }

    public static void main(String[] args) {
        List<String> source = List.of(
                "  an  ", "", "Binh", " an ", "Lan", "bao");

        List<String> fromLoop = withLoop(source);
        List<String> fromStream = withStream(source);

        System.out.println("loop=" + fromLoop);
        System.out.println("stream=" + fromStream);
        System.out.println("same=" + fromLoop.equals(fromStream));
        System.out.println("source-size=" + source.size());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac StreamOrLoopDemo.java
java StreamOrLoopDemo
~~~

Stdout dự kiến chính xác:

~~~text
loop=[AN, BINH, LAN, BAO]
stream=[AN, BINH, LAN, BAO]
same=true
source-size=6
~~~

### Phân tích lựa chọn

- Vòng lặp diễn đạt rõ một phiên duyệt, phép chuẩn hóa, kiểm tra rỗng, tập `seen` và việc thêm vào kết quả.
- Stream trình bày tuyến biến đổi từ đầu vào sang kết quả bằng các operation có tên, không đòi người đọc theo dõi biến `seen` và `result`.
- `distinct()` trên stream có encounter order giữ phần tử đầu tiên trong mỗi nhóm bằng nhau, tương ứng với `LinkedHashSet` trong ví dụ.
- `Locale.ROOT` giúp phép uppercase không dựa vào locale mặc định, làm ví dụ ổn định.
- `source` chỉ chứa các `String` không null; nếu cho phép null, **cả hai cách cần xử lý null rõ ràng** trước `trim()`.
- Danh sách từ `Stream.toList()` là **unmodifiable**; `ArrayList` từ vòng lặp có thể sửa. Hai cách hiện tại cho **nội dung giống nhau**, nhưng chưa có **hợp đồng mutability giống nhau**. Đây là khác biệt cần xét trước khi thay thế trong production.

Nếu contract yêu cầu `List` có thể sửa, đổi terminal Stream thành `collect(Collectors.toCollection(ArrayList::new))`. Nếu contract cần danh sách không sửa được ở cả hai cách, có thể trả `List.copyOf(result)` ở nhánh vòng lặp khi dữ liệu thích hợp. **Tính tương đương không chỉ là `equals` của kết quả**.

## 6. Stream làm nổi bật kiểu biến đổi, vòng lặp làm nổi bật biến trạng thái

Một cách đánh giá nhanh là xem biến nào người đọc phải theo dõi.

Với Stream:

~~~java
orders.stream()
        .filter(Order::isPaid)
        .mapToLong(Order::amount)
        .sum();
~~~

các giá trị tạm được truyền qua pipeline; thông thường không có biến mutable bên ngoài. Người đọc tập trung vào kiểu dữ liệu và operator.

Với vòng lặp:

~~~java
long sum = 0;
for (Order order : orders) {
    if (order.isPaid()) {
        sum += order.amount();
    }
}
~~~

chỉ một biến trạng thái `sum` và một nhánh. Nó cũng rất rõ ràng. Không có lý do kỹ thuật để kết luận một trong hai “kém chuyên nghiệp” hơn.

Nhưng nếu vòng lặp có bảy biến cập nhật, bốn mức lồng và nhiều nhánh `continue`, hãy xem có thể tách một phần lọc/biến đổi thành hàm hay Stream không. Ngược lại, nếu một Stream phải giữ state qua `AtomicReference`, `StringBuilder` bên ngoài và `peek`, thử viết lại bằng vòng lặp. **Cần tối ưu ý nghĩa, không tối ưu số dấu ngoặc.**

## 7. Dừng sớm: `break`/`return` và Stream short-circuit

Vòng lặp có thể dừng bằng `break`, `return` hoặc tiếp tục bằng `continue`. Stream cung cấp nhiều terminal short-circuit:

- `findFirst()`: lấy phần tử đầu tiên theo encounter order nếu có.
- `findAny()`: lấy một phần tử bất kỳ; không cam kết là đầu tiên, đặc biệt trong parallel.
- `anyMatch(predicate)`: dừng khi tìm được phần tử thỏa.
- `allMatch(predicate)`: dừng khi tìm được phần tử **không** thỏa.
- `noneMatch(predicate)`: dừng khi tìm được phần tử thỏa.

Các phép `limit` và `takeWhile` là intermediate có thể giới hạn việc xử lý; `takeWhile` được thêm từ Java 9. Không phải mọi terminal cần duyệt toàn bộ nguồn.

Ví dụ:

~~~java
boolean hasInvalid = values.stream()
        .anyMatch(value -> value < 0);
~~~

Điều kiện này đơn giản và dễ đọc; Stream có ưu thế vì không cần biến mutable `hasInvalid` và nhánh `break`.

Trong tình huống cần **vị trí đầu tiên** của dữ liệu không hợp lệ, vòng lặp dùng index trực tiếp; Stream có thể dùng `IntStream.range(...)`, nhưng độ rõ ràng phụ thuộc mức phức tạp.

## 8. Ví dụ chạy đầy đủ 2: tìm vị trí lỗi đầu tiên

Tạo file **EarlyExitChoiceDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class EarlyExitChoiceDemo {

    public static void main(String[] args) {
        List<String> values =
                List.of("ok", " ready ", " ", "accepted");

        int firstBadLoop = -1;
        int checkedLoop = 0;

        for (int i = 0; i < values.size(); i++) {
            checkedLoop++;
            if (values.get(i).isBlank()) {
                firstBadLoop = i;
                break;
            }
        }

        int firstBadStream = IntStream.range(0, values.size())
                .filter(i -> values.get(i).isBlank())
                .findFirst()
                .orElse(-1);

        System.out.println("loop-index=" + firstBadLoop);
        System.out.println("stream-index=" + firstBadStream);
        System.out.println("loop-checked=" + checkedLoop);
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac EarlyExitChoiceDemo.java
java EarlyExitChoiceDemo
~~~

Stdout:

~~~text
loop-index=2
stream-index=2
loop-checked=3
~~~

Hai cách đều tìm được vị trí 2. Với vòng lặp, `checkedLoop` diễn đạt rõ số lần đã kiểm tra. Với Stream, `IntStream.range(...).filter(...).findFirst()` diễn đạt ý định **vị trí đầu tiên thỏa điều kiện**. Trong ví dụ tuần tự này, `findFirst()` dừng khi tìm được chỉ số 2.

**Không thêm biến đếm bên ngoài `filter` để “tái tạo” `checkedLoop` nếu nó không phục vụ yêu cầu nghiệp vụ.** Bộ đếm side effect dễ gây nhầm lẫn khi pipeline được tối ưu hoặc chuyển sang parallel. Nếu số phần tử đã kiểm tra thật sự là output cần thiết, vòng lặp hoặc một thuật toán trả kết quả có cấu trúc sẽ rõ và đáng tin hơn.

### Lưu ý về `Optional` và kết quả không có phần tử

`IntStream.findFirst()` trả `OptionalInt`; `orElse(-1)` tạo sentinel khi không tìm thấy lỗi. Chỉ dùng `-1` khi hợp đồng đã quy định nó nghĩa là “không có vị trí”. Một API phức tạp có thể trả `OptionalInt` ra ngoài thay vì che sự vắng mặt thành một số nguyên đặc biệt.

## 9. Trạng thái tích lũy theo từng bước: vòng lặp thường thắng về độ rõ ràng

Không phải mọi phép “gộp” đều nên trở thành `reduce` hoặc `collect`. Các phép gom với toán tử kết hợp rõ ràng như tổng, max, nhóm theo key có collector phù hợp. Nhưng thuật toán **phụ thuộc thứ tự và quyết định dựa trên trạng thái trước đó** đôi khi hợp với vòng lặp hơn.

Ví dụ: gom dãy số thành các nhóm liên tiếp; tổng mỗi nhóm không vượt `7`. Khi thêm một số khiến tổng vượt `7`, chốt nhóm hiện tại rồi mở nhóm mới. Đây là quy trình greedy có ranh giới và trạng thái tường minh.

Một phiên bản Stream bằng `forEach` và trạng thái mutable bên ngoài không tự tốt hơn. Trong parallel stream, logic giữ nhóm theo thứ tự càng khó đúng. Vòng lặp làm rõ việc các phần tử **phải được duyệt theo thứ tự** và ranh giới nhóm **phụ thuộc kết quả trước đó**.

## 10. Ví dụ chạy đầy đủ 3: thuật toán phân nhóm có trạng thái

Tạo tệp **StatefulGroupingLoopDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StatefulGroupingLoopDemo {

    static List<List<Integer>> batchByLimit(
            List<Integer> numbers, int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }

        List<List<Integer>> groups = new ArrayList<>();
        List<Integer> current = new ArrayList<>();
        int sum = 0;

        for (int number : numbers) {
            if (number <= 0 || number > limit) {
                throw new IllegalArgumentException(
                        "number out of range: " + number);
            }

            if (!current.isEmpty() && sum + number > limit) {
                groups.add(List.copyOf(current));
                current.clear();
                sum = 0;
            }

            current.add(number);
            sum += number;
        }

        if (!current.isEmpty()) {
            groups.add(List.copyOf(current));
        }

        return List.copyOf(groups);
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(4, 3, 5, 2, 1);
        List<List<Integer>> groups = batchByLimit(values, 7);

        System.out.println("groups=" + groups);
        System.out.println("count=" + groups.size());
    }
}
~~~

Lệnh chạy:

~~~bash
javac StatefulGroupingLoopDemo.java
java StatefulGroupingLoopDemo
~~~

Stdout:

~~~text
groups=[[4, 3], [5, 2], [1]]
count=3
~~~

Vì sao chọn vòng lặp?

1. `current` và `sum` là trạng thái có mục đích rõ ràng.
2. Mỗi số phải được xử lý đúng thứ tự xuất hiện.
3. Điều kiện chốt nhóm và reset được nhìn thấy tại cùng vị trí.
4. Validation đầu vào nằm ngay trước thao tác cộng vào nhóm.
5. Kết quả trả về là bản sao không sửa được ở các tầng được tạo, giảm nguy cơ caller chỉnh nhóm sau khi xây.
6. Một pipeline Stream có side effects ghi vào `current` và `groups` sẽ khó dùng đúng với parallel và không làm giảm phức tạp thuật toán.

Nếu cần tính tổng toàn bộ số đơn thuần, `numbers.stream().mapToInt(Integer::intValue).sum()` mới là ví dụ phù hợp của Stream. **Sự lựa chọn phụ thuộc cấu trúc bài toán**, không phụ thuộc việc dữ liệu có ở dạng List hay không.

## 11. Phân nhóm/tổng hợp nhiều phần tử: Stream có collector sẵn rất tiện

Java Stream mạnh ở các bài toán `groupingBy`, `partitioningBy`, `joining`, `summingInt`, `mapping`. Chúng thể hiện mục tiêu tổng hợp tập dữ liệu mà không cần người đọc theo dõi cách tạo và cập nhật `Map`.

Ví dụ:

~~~java
// Mảnh mã minh họa, Invoice là record có category() và amount().
Map<String, Integer> totals = invoices.stream()
        .collect(Collectors.groupingBy(
                Invoice::category,
                TreeMap::new,
                Collectors.summingInt(Invoice::amount)));
~~~

Nghĩa là “nhóm hóa đơn theo category, sắp xếp key theo thứ tự tự nhiên và cộng amount trong mỗi nhóm”. Nếu nhóm đã dùng collectors thành thạo, cách viết này rất rõ.

Vòng lặp có thể đơn giản không kém khi logic là phép merge:

~~~java
// Mảnh mã minh họa:
Map<String, Integer> totals = new TreeMap<>();
for (Invoice item : invoices) {
    totals.merge(item.category(), item.amount(), Integer::sum);
}
~~~

Hai cách đều hợp lý; không nên tranh luận theo sở thích nếu cả hai đều có ý nghĩa tốt. Cần xem xét null keys, overflow của `int`, hợp đồng `Map` được trả về, tính thread-safe và loại `Map` khi dùng trong sản phẩm thật.

## 12. Ví dụ chạy đầy đủ 4: tổng hợp bằng Stream và vòng lặp

Tạo file **StreamVsLoopGroupingDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StreamVsLoopGroupingDemo {

    record Invoice(String category, int amount) {}

    static Map<String, Integer> totalsWithLoop(
            List<Invoice> invoices) {
        Map<String, Integer> totals = new TreeMap<>();
        for (Invoice invoice : invoices) {
            totals.merge(invoice.category(),
                    invoice.amount(),
                    Integer::sum);
        }
        return totals;
    }

    static Map<String, Integer> totalsWithStream(
            List<Invoice> invoices) {
        return invoices.stream().collect(Collectors.groupingBy(
                Invoice::category,
                TreeMap::new,
                Collectors.summingInt(Invoice::amount)));
    }

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
                new Invoice("book", 20),
                new Invoice("pen", 3),
                new Invoice("book", 7),
                new Invoice("pen", 2));

        Map<String, Integer> loop = totalsWithLoop(invoices);
        Map<String, Integer> stream = totalsWithStream(invoices);

        System.out.println("loop=" + loop);
        System.out.println("stream=" + stream);
        System.out.println("same=" + loop.equals(stream));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StreamVsLoopGroupingDemo.java
java StreamVsLoopGroupingDemo
~~~

Stdout chính xác:

~~~text
loop={book=27, pen=5}
stream={book=27, pen=5}
same=true
~~~

Ở đây `TreeMap` được chọn để thứ tự key in ra ổn định trong ví dụ. Cả hai method trả một `Map` có thể thay đổi. `Collectors.groupingBy` không được mặc định là `TreeMap` nếu bạn không chỉ định map factory như trong ví dụ; loại map có thể khác theo collector.

Nếu có tổng tiền lớn, `int` có thể overflow; thiết kế thực tế cân nhắc `long`, `BigDecimal` hoặc kiểu tiền tệ phù hợp, dù dùng Stream hay vòng lặp.

## 13. Độ rõ ràng trong xử lý ngoại lệ

Một pipeline có chuỗi như:

~~~java
inputs.stream()
        .map(Integer::parseInt)
        .filter(n -> n > 0)
        .toList();
~~~

sẽ ném `NumberFormatException` nếu gặp input không phải số nguyên hợp lệ. Nếu yêu cầu là **fail fast** ở input sai đầu tiên, hành vi đó có thể phù hợp. Nếu yêu cầu là thu thập **tất cả lỗi** và vẫn trả các giá trị hợp lệ, một vòng lặp với `try/catch` rõ ràng thường dễ đọc hơn.

Với Stream, có thể viết helper chuyển `String` thành một result object biểu diễn thành công/thất bại và tiếp tục gom bằng collector, nhưng không nên tạo cả hệ thống wrapper chỉ để tránh một vòng lặp 12 dòng. Nếu dữ liệu parse được tái sử dụng ở nhiều nơi, kiểu `ParseResult` và các hàm `map`/ `flatMap` lại có thể là thiết kế đáng giá.

### Không giấu lỗi trong lambda

Tránh pattern:

~~~java
// Mảnh mã minh họa về cách xử lý lỗi thiếu hợp đồng:
inputs.stream().map(s -> {
    try {
        return Integer.parseInt(s);
    } catch (NumberFormatException ex) {
        return 0;
    }
});
~~~

Giá trị `0` có thể là dữ liệu hợp lệ hoặc đầu vào không hợp lệ; cả hai bị gộp lại khiến consumer không biết nguyên nhân. Nếu quyết định fallback về 0 là một yêu cầu nghiệp vụ thật, cần tài liệu hóa và kiểm thử; không dùng nó chỉ để tránh exception trong `map`.

## 14. Ví dụ chạy đầy đủ 5: parse, lọc và ghi nhận lỗi

Tạo file **ParsingWithLoopDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ParsingWithLoopDemo {

    public static void main(String[] args) {
        List<String> source =
                List.of("7", "bad", "11", "-2", "0");

        List<Integer> accepted = new ArrayList<>();
        List<String> invalid = new ArrayList<>();
        int nonPositive = 0;

        for (String raw : source) {
            try {
                int value = Integer.parseInt(raw);
                if (value <= 0) {
                    nonPositive++;
                    continue;
                }
                accepted.add(value);
            } catch (NumberFormatException ex) {
                invalid.add(raw);
            }
        }

        System.out.println("accepted=" + accepted);
        System.out.println("invalid=" + invalid);
        System.out.println("non-positive=" + nonPositive);
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac ParsingWithLoopDemo.java
java ParsingWithLoopDemo
~~~

Stdout:

~~~text
accepted=[7, 11]
invalid=[bad]
non-positive=2
~~~

Điểm mạnh của vòng lặp ở đây là **ba kết quả độc lập** có cách xây khác nhau: giá trị dương hợp lệ, input không parse được, và số lượng giá trị không dương. Người đọc thấy rõ rằng `bad` không bị biến âm thầm thành `0`.

Về mặt thiết kế production, nếu danh sách lỗi cần có vị trí dòng hoặc nguyên nhân, có thể dùng record `InvalidRow(int index, String input, String reason)` rồi thêm vào `invalid`. Nếu cần phép parse này ở nhiều chỗ, tách helper trả một kiểu kết quả có trạng thái rõ thay vì lặp lại `try/catch` ở nhiều nơi.

## 15. Side effects, `peek` và mối nguy “vòng lặp ẩn” trong Stream

`Stream.peek(Consumer)` là intermediate, thường hữu ích cho quan sát khi debug, nhưng **không nên dùng cho hành vi bắt buộc**:

~~~java
// Mảnh mã minh họa về điều KHÔNG nên giả định:
long count = values.stream()
        .peek(v -> audit(v))
        .count();
~~~

`count()` có thể tối ưu hóa khi số phần tử xác định được mà không cần duyệt toàn bộ pipeline. Java không cam kết mỗi `audit(v)` đều được chạy. Tương tự, một terminal short-circuit như `findFirst` không cần đi hết nguồn; `peek` không thể dùng như cam kết “mỗi phần tử được ghi log”.

Nếu mỗi phần tử phải được xử lý bằng side effect chính, ví dụ lưu một bản ghi vào database và cập nhật trạng thái tiến độ, có thể chọn vòng lặp:

~~~java
// Mảnh mã minh họa:
for (Record record : records) {
    repository.save(record);
    progress.increment();
}
~~~

Vòng lặp khiến thứ tự gọi rõ, dễ định nghĩa retry/rollback. Nếu dùng Stream `forEach` cho hành vi này, vẫn phải quản lý ngoại lệ, thứ tự, transaction và concurrency tương tự; Stream không tự làm những việc đó.

### `forEach` không phải luôn sai

Khi chỉ cần in một số giá trị hoặc gọi một callback đơn giản, `stream.forEach(action)` là terminal hợp lệ. Nhưng nếu logic phức tạp, việc chọn vòng lặp không hề “lạc hậu”. Đặc biệt trên `parallelStream`, `forEach` không bảo đảm thứ tự gặp phần tử; nếu cần thứ tự, `forEachOrdered` có bảo đảm liên quan encounter order nhưng có thể giảm lợi ích của song song.

### Không sửa nguồn đang được duyệt

Với cả hai cách, sửa collection trực tiếp trong lúc duyệt không đúng cách có thể gây lỗi. Stream yêu cầu các behavioral parameters của phần lớn operation là **non-interfering** và **stateless**. Nếu bạn cần xóa phần tử ngay khi duyệt trong vòng lặp, có thể dùng `Iterator.remove()` phù hợp loại collection thay vì sửa bằng `list.remove(...)` không đúng lúc. Nếu muốn tạo danh sách mới, Stream `filter` hoặc vòng lặp xây `new ArrayList` thường rõ hơn.

## 16. Tránh lồng Stream chỉ để thay vòng lặp lồng nhau

Dữ liệu nhiều tầng như `List<List<T>>` là trường hợp `flatMap` hữu ích:

~~~java
List<Integer> values = groups.stream()
        .flatMap(List::stream)
        .toList();
~~~

Nếu yêu cầu là “trải phẳng tất cả phần tử”, một dòng `flatMap` có thể rất dễ đọc. Nhưng khi cần gắn mỗi phần tử với **chỉ số nhóm, chỉ số phần tử, trạng thái phân trang** và phân loại lỗi ở từng cấp, vòng lặp lồng nhau với hai chỉ số có thể phản ánh yêu cầu tốt hơn:

~~~java
// Mảnh mã minh họa:
for (int groupIndex = 0; groupIndex < groups.size(); groupIndex++) {
    List<Item> group = groups.get(groupIndex);
    for (int itemIndex = 0; itemIndex < group.size(); itemIndex++) {
        process(groupIndex, itemIndex, group.get(itemIndex));
    }
}
~~~

Đừng mặc định nested loops là một “code smell”. Điều nên xem xét là các tầng lồng có diễn đạt một quan hệ nghiệp vụ có thật hay chỉ là sản phẩm của việc tổ chức code chưa tốt.

Nếu chỉ cần flatten, Stream thường ngắn và rõ; nếu cần state/indices/điều khiển từng tầng, loop thường trực quan.

## 17. Null, dữ liệu rỗng và tính tương đương của hai cách

Khi so sánh Stream và vòng lặp, cần xét cả trường hợp biên.

### Null trong nguồn

`Stream.of((String) null)` chứa **một phần tử null**; đó không phải stream rỗng. `map(String::trim)` hoặc `map(String::length)` gặp phần tử null sẽ ném `NullPointerException`. Với vòng lặp, gọi `name.trim()` trên null cũng vậy.

Nếu hợp đồng cho phép null:

~~~java
List<String> result = values.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .toList();
~~~

Đây là mảnh mã minh họa cần import `Objects`. Vòng lặp tương ứng sẽ kiểm tra `name == null` và `continue`.

### Empty stream

`count()` trả 0; `findFirst()` trả `Optional.empty()`; `anyMatch` trả false; `allMatch` và `noneMatch` trả true với stream rỗng. Nếu nghiệp vụ yêu cầu “ít nhất một phần tử và tất cả hợp lệ”, chỉ dùng `allMatch` là chưa đủ.

Vòng lặp cũng phải có chính sách với danh sách rỗng; không có cấu trúc nào tự hiểu business requirement.

### Mutability, thứ tự, duplicates

Hai kết quả có thể cùng nội dung nhưng khác hợp đồng:

- `stream.toList()` từ Java 16 trả List **unmodifiable**.
- `stream.collect(Collectors.toList())` không hứa List có thể sửa hay kiểu implementation cụ thể.
- Vòng lặp với `new ArrayList<>()` trả List có thể sửa.
- `distinct()` trên ordered stream giữ phần tử đầu tiên tương ứng encounter order; một `HashSet` trong vòng lặp **không tự** bảo đảm cùng thứ tự đó.
- `sorted()` có thể thay đổi thứ tự; không bỏ nó khi chuyển sang loop nếu thứ tự đầu ra là một phần contract.
- Nếu object là mutable, danh sách unmodifiable **không** làm object bên trong bất biến sâu.

Khi refactor giữa Stream và loop, hãy viết test cho cả **giá trị**, **thứ tự**, **duplicates**, **null**, **empty case**, **mutability** và **ngoại lệ**, chứ không chỉ so `equals` của một ví dụ đẹp.

## 18. Tài nguyên và vòng đời dữ liệu

Stream có thể gắn với tài nguyên bên ngoài như tệp:

~~~java
// Mảnh mã minh họa, có path kiểu Path và import cần thiết.
try (Stream<String> lines = Files.lines(path)) {
    long valid = lines.filter(line -> !line.isBlank()).count();
    System.out.println(valid);
}
~~~

Nguồn `Files.lines` nên được đóng bằng try-with-resources. **Gọi terminal không tự có nghĩa stream đã được đóng.** Nếu chuyển sang vòng lặp đọc `BufferedReader`, vẫn cần try-with-resources đúng. Sự lựa chọn Stream/loop không miễn trách nhiệm giải phóng tài nguyên.

Một Stream là **one-shot**: sau terminal, không được sử dụng lại cho terminal khác. Với collection nguồn có thể duyệt lại, gọi `collection.stream()` thêm lần nữa; với file I/O, phải xác định việc mở/đọc mới có hợp lệ không.

### Khi nào loop thuận lợi hơn cho I/O?

Nếu mỗi dòng cần quyết định đọc tiếp hay ngừng, xử lý lỗi theo số dòng, checkpoint hay hủy tác vụ, một vòng lặp `while ((line = reader.readLine()) != null)` có thể rất trực quan. Stream `Files.lines(...)` phù hợp khi bạn muốn các phép biến đổi trên dòng và dùng tài nguyên đúng scope.

Không ép việc xử lý file có nhiều bước trạng thái thành một pipeline lồng `map`/ `peek` nếu làm cho điều kiện dừng và cleanup khó nhận thấy.

## 19. Song song không phải tiêu chí mặc định để chọn Stream

Một lợi thế của Stream API là hỗ trợ chế độ parallel bằng `parallelStream()` hoặc `parallel()`. Nhưng **bật parallel không tự bảo đảm nhanh hơn** và không phải giải pháp mặc định cho bài toán có hiệu năng chưa đo.

Những yếu tố có thể khiến parallel kém hiệu quả hoặc sai logic:

- Nguồn quá nhỏ so với chi phí tách/gộp task.
- Các thao tác rất rẻ, overhead chiếm ưu thế.
- `sorted`, `distinct` hay `limit` có ràng buộc thứ tự và state.
- Bộ tích lũy dùng chung không thread-safe.
- Side effects vào database, network, logs hoặc UI có yêu cầu thứ tự.
- Dữ liệu cần xử lý theo trình tự (state machine, phụ thuộc phần tử trước).
- Nguồn khó chia hoặc xử lý I/O bị nghẽn tài nguyên.

Nếu bài toán thiên về CPU, dữ liệu lớn, operation độc lập, accumulator/collector đáp ứng yêu cầu kết hợp và có phép đo xác nhận, parallel stream có thể đáng xem xét. Nhưng khi mục tiêu là **độ rõ ràng**, không nên biến một vòng lặp tuần tự dễ hiểu thành parallel pipeline chỉ vì API cho phép.

### Thứ tự trong parallel

~~~java
List.of(1, 2, 3, 4).parallelStream()
        .forEach(System.out::println);
~~~

Không có stdout thứ tự cố định. Nếu cần giữ encounter order, `forEachOrdered` có ràng buộc đó, nhưng không nên dựa vào parallel để thực hiện chuỗi side effects phải diễn ra có thứ tự mạnh.

Vòng lặp tuần tự là lựa chọn rất tự nhiên khi tính đúng đắn phụ thuộc thứ tự.

## 20. Hiệu năng: đo trước, tối ưu sau

Không có kết luận luôn đúng rằng Stream **nhanh hơn** hoặc vòng lặp **nhanh hơn**.

Hiệu năng còn phụ thuộc:

1. **Dạng dữ liệu**: mảng primitive, `List<Integer>`, `ArrayList`, `LinkedList`, `HashSet`, tệp I/O.
2. **Số phần tử**: vài mục so với hàng triệu mục.
3. **Độ phức tạp phép biến đổi**: gọi method vài nanosecond hay truy vấn network.
4. **Boxing/unboxing**: `Stream<Integer>` khác `IntStream`.
5. **Tối ưu hóa JIT**: JVM có thể inline một số lambda và loại bỏ allocation, nhưng kết quả phụ thuộc workload.
6. **Tính lazy và short-circuit**: `findFirst`, `anyMatch` có thể tránh đi hết nguồn.
7. **Thao tác stateful**: `sorted`/`distinct` có thể cần bộ nhớ và chi phí điều phối.
8. **Parallelism**: overhead, thread scheduling và contention.
9. **Bộ nhớ**: danh sách kết quả, các cấu trúc tạm và khả năng garbage collection.
10. **Compiler/JDK version và flags**: hiệu năng có thể khác qua môi trường.

Nếu cần benchmark Java nghiêm túc, dùng một harness như **JMH** với warmup, nhiều iteration, dữ liệu đại diện và cách ngăn dead-code elimination. Không kết luận từ một lần `System.nanoTime()` quanh vòng lặp nhỏ vì JIT warmup, GC và tối ưu hóa có thể làm số đo không đáng tin.

### Primitive stream và boxing

Nếu bài toán tính tổng `int` đơn giản:

~~~java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

`mapToInt` chuyển sang primitive stream, tránh tạo một `Stream<Integer>` mới ở các bước phía sau một cách không cần thiết. Tuy nhiên, chỉ đo mới biết nó hơn hay kém vòng lặp `int total = 0; for (int n : numbers) total += n;` trong bối cảnh thực tế.

Nếu tổng có thể vượt `int`, cần chuyển sang `long` hoặc kiểu số thích hợp. Cả vòng lặp và Stream đều cần hiểu giới hạn kiểu.

## 21. Những trường hợp quy tắc “Stream cho dữ liệu, loop cho điều khiển” cần điều chỉnh

Đó chỉ là heuristic, không phải luật.

**Stream có thể rất rõ khi tìm kiếm dừng sớm:**

~~~java
Optional<User> user = users.stream()
        .filter(User::isActive)
        .findFirst();
~~~

Nếu yêu cầu đúng là “người dùng active đầu tiên”, đây là mã rõ ràng. Vòng lặp với `return Optional.of(user)` cũng rõ; nhóm có thể chọn theo thói quen.

**Vòng lặp có thể rất rõ khi biến đổi đơn giản:**

~~~java
List<String> upper = new ArrayList<>();
for (String word : words) {
    upper.add(word.toUpperCase(Locale.ROOT));
}
~~~

Một vòng lặp không bị “lỗi thời” vì có `map` tương đương. Ngược lại, nếu hiện tại đã có nhiều bước liên tiếp, Stream có thể giảm các biến tạm và nesting.

**Một method có thể kết hợp cả hai:**

~~~java
// Mảnh mã minh họa:
List<Task> ready = tasks.stream()
        .filter(Task::isReady)
        .toList();

for (Task task : ready) {
    executeWithRetry(task);
}
~~~

Ở đây Stream chuẩn bị danh sách theo điều kiện thuần, vòng lặp vận hành các side effects có retry. Chỉ làm như vậy khi việc materialize `ready` là hợp lý: nó tạo một danh sách trung gian và có thể tiêu tốn bộ nhớ. Với nguồn rất lớn, có thể cân nhắc duyệt trực tiếp trong vòng lặp với điều kiện lọc để tránh gom toàn bộ.

Đôi khi **tách pipeline và workflow** thành hai phase rõ ràng quan trọng hơn việc chọn độc quyền một công cụ.

## 22. Review code theo tiêu chí có thể kiểm chứng

Khi hai cách viết đều hoạt động, thay vì nêu cảm giác “ngắn hơn” hoặc “đẹp hơn”, hãy hỏi:

| Tiêu chí | Câu hỏi |
| --- | --- |
| Ý nghĩa | Chỉ cần đọc tên operator có hiểu chính xác yêu cầu không? |
| State | Có phải theo dõi nhiều biến thay đổi qua từng phần tử không? |
| Control flow | Có `break`/`continue`/`return`/exception theo nhiều nhánh không? |
| Side effect | Có network/DB/logging bắt buộc theo thứ tự không? |
| Kết quả | Có cần một List/Map mới hay chỉ cần hành động? |
| Null/empty | Hành vi với null và nguồn rỗng có hiển nhiên không? |
| Order | Encounter order, sorted order và ưu tiên đầu tiên có được giữ không? |
| Mutability | Kết quả có thể sửa không, có chia sẻ object mutable không? |
| Resources | Stream/file/reader có được đóng đúng lúc không? |
| Concurrency | Nếu dùng parallel, phép biến đổi có stateless/non-interfering không? |
| Testing | Có thể xác minh đầu ra, ngoại lệ và ranh giới bằng test nhỏ không? |
| Performance | Có dữ liệu benchmark đáng tin nếu hiệu năng là lý do refactor không? |

Một review tốt xem **contract bên ngoài** của method, không chỉ nhìn phần thân. Chuyển `ArrayList` thành `Stream.toList()` có thể phá caller muốn `add`; chuyển vòng lặp cập nhật tuần tự thành `parallelStream().forEach(...)` có thể đổi thứ tự side effects. Những khác biệt này quan trọng hơn số dòng code.

## 23. Sai lầm thường gặp

| Sai lầm | Vì sao chưa đúng | Cách sửa |
| --- | --- | --- |
| “Java hiện đại luôn phải dùng Stream” | Vòng lặp vẫn là cú pháp cốt lõi | Chọn cách làm rõ business intent |
| “Vòng lặp luôn nhanh hơn Stream” | Hiệu năng phụ thuộc workload/JVM | Benchmark trên dữ liệu thật |
| “Stream ngắn hơn tức dễ đọc hơn” | Lambda dài/lồng sâu có thể khó hiểu | Tách helper hoặc dùng loop |
| “`peek` thích hợp cho audit bắt buộc” | Intermediate side effect không được bảo đảm mọi trường hợp | Dùng quy trình side effect tường minh |
| “`forEach` tương đương loop với mọi nguồn” | Thứ tự/parallel/exceptions có thể khác | Kiểm tra encounter order và contract |
| “Mọi bài toán stateful đều nên dùng `reduce`” | Mutable accumulator dễ sai, đặc biệt parallel | Dùng loop hoặc collector phù hợp |
| “`findAny` luôn là phần tử đầu” | Không có cam kết đó | Dùng `findFirst` nếu cần |
| “`allMatch` trả false khi nguồn rỗng” | Với nguồn rỗng nó trả true | Kiểm tra non-empty riêng |
| “`toList()` giống `new ArrayList`” | Kết quả unmodifiable | Chọn terminal/copy đúng |
| “`Collectors.toList()` luôn mutable” | Không có hợp đồng mutability cụ thể | Dùng `toCollection(ArrayList::new)` |
| “Đưa `limit` lên trước `sorted` vẫn như cũ” | Kết quả có thể khác | Bảo toàn thứ tự operation |
| “Dùng Stream rồi gọi nhiều terminal trên cùng object” | Stream one-shot | Tạo Stream mới |
| “Parallel là tối ưu miễn phí” | Overhead và side effects có thể hại | Chứng minh tính đúng và đo hiệu năng |
| “Source có null thì Stream tự bỏ null” | Null vẫn là phần tử hợp lệ ở nhiều nguồn | Lọc/validate theo contract |
| “Code chạy một test mẫu là đủ” | Có thể khác ở empty/duplicate/order/exception | Test các trường hợp biên |

## 24. Bài tập thực hành có hướng dẫn

**Bài 1 — So sánh hành vi và contract.** Viết một phép lọc tên bằng vòng lặp `ArrayList` và bằng Stream `toList()`. Kiểm tra giá trị, thứ tự, duplicate, null, empty input và thử `add` vào kết quả. Giải thích vì sao hai list bằng nhau theo `equals` chưa bảo đảm thay thế API là an toàn.

**Bài 2 — Short-circuit.** Với danh sách số nguyên, tìm số âm đầu tiên bằng vòng lặp `break` và bằng `filter(...).findFirst()`. Thử nguồn rỗng, danh sách không có số âm, số âm ở đầu và cuối. Khi nào vòng lặp có thể rõ hơn vì cần thêm index?

**Bài 3 — Gom nhóm.** Với hóa đơn có `category` và `amount`, tính tổng theo nhóm bằng `Map.merge` trong vòng lặp và `Collectors.groupingBy(..., summingInt(...))`. Dùng `TreeMap` cho output ổn định. Kiểm tra nhóm không có phần tử và các giá trị lớn gây overflow.

**Bài 4 — Logic trạng thái.** Với dãy `4,3,5,2,1` và giới hạn nhóm 7, cài đặt chia nhóm bằng vòng lặp. Thử giới hạn 0, phần tử âm và phần tử lớn hơn giới hạn. Giải thích vì sao `parallelStream` không phù hợp nếu nhóm phải giữ thứ tự.

**Bài 5 — Xử lý lỗi parse.** Nhận chuỗi số, tách số dương hợp lệ, chuỗi không parse được và số không dương. Viết vòng lặp rõ ràng. Sau đó thử thiết kế `ParseResult` có trạng thái thành công/thất bại rồi dùng Stream; đánh giá cách nào dễ bảo trì với số rule hiện có.

**Bài 6 — Phân tích side effect.** Viết pipeline `Stream.of(1,2,3).peek(log).count()` và dự đoán liệu `log` có chắc được gọi ba lần không. Giải thích tại sao không được dùng cách đó làm audit. Chọn cấu trúc phù hợp nếu phải bảo đảm mỗi record đã được xử lý.

**Bài 7 — Nested data.** Dùng `flatMap` lấy tất cả item từ `List<List<Item>>`. Sau đó cần ghi lỗi kèm `groupIndex` và `itemIndex` rồi dừng ở lỗi đầu: so sánh với hai vòng lặp for có chỉ số.

**Bài 8 — Tài nguyên.** Viết code đếm dòng không rỗng từ `Files.lines(path)` trong try-with-resources. Viết lại bằng `BufferedReader` và vòng lặp `while`. Cả hai có đóng tài nguyên khi lỗi phát sinh không?

**Bài 9 — Benchmark.** Thiết kế một microbenchmark dùng JMH so sánh tổng số từ một `int[]`, một `List<Integer>` và một phép biến đổi tốn CPU. Nêu các biến cần giữ giống nhau và cách tránh dead-code elimination. Không đo bằng một lần `nanoTime` rồi đưa ra kết luận chung.

**Bài 10 — Chọn giải pháp cho API thực tế.** Một batch service phải lọc task sẵn sàng, gọi external API từng task, retry có giới hạn, ghi checkpoint và dừng khi gặp lỗi nghiêm trọng. Đề xuất pipeline lọc thuần + vòng lặp side effect hoặc vòng lặp duy nhất; phân tích chi phí tạo danh sách tạm.

## 25. Checklist quyết định nhanh

- Yêu cầu có thể đọc như một chuỗi **filter/map/collect** thuần không?
- Dữ liệu có nhiều trạng thái cần thay đổi qua từng phần tử không?
- Có cần `break`, `continue`, return sớm hoặc xử lý lỗi phức tạp không?
- Có side effects **bắt buộc** và yêu cầu thứ tự cụ thể không?
- Có dùng `peek` hay lambda sửa state bên ngoài chỉ để giữ Stream không?
- Kết quả mong muốn là List, Map, tổng, phần tử đầu tiên, boolean hay một workflow?
- Nếu refactor, đã giữ đúng order, null/empty, duplicates, mutability và ngoại lệ chưa?
- Nếu đọc file hoặc tài nguyên I/O, lifecycle đóng tài nguyên có rõ chưa?
- Nếu dùng parallel, các operation có stateless và không can thiệp nguồn không?
- Nếu mục tiêu là hiệu năng, đã có benchmark đại diện thay vì trực giác chưa?
- Code của đồng đội sẽ hiểu nhanh hơn với cấu trúc nào trong sáu tháng tới?
- Các API chọn có phù hợp JDK của dự án không? Với Java 8 thuần, thay `toList()` bằng collector thích hợp; với Java 17+ có thể dùng API mới hiện vẫn được hỗ trợ.

## 26. Kết luận

**Stream** thường sáng rõ khi bài toán là xử lý tập hợp theo pipeline khai báo, với các thao tác `filter`, `map`, `flatMap`, `distinct`, `sorted`, `collect`, `toList`, `reduce` hoặc phép tìm kiếm ngắn gọn. **Vòng lặp** thường sáng rõ khi thuật toán có trạng thái qua từng phần tử, nhiều điểm dừng, ngoại lệ theo bước hoặc tác vụ side effect tuần tự.

Không có lựa chọn đúng cho mọi trường hợp. So sánh bằng **hợp đồng đầu ra, cách người đọc suy luận về dữ liệu và trạng thái, điều kiện biên, khả năng kiểm thử và số đo hiệu năng khi cần**. Việc giữ một vòng lặp có ý nghĩa là quyết định Java hiện đại hoàn toàn hợp lý; việc thay một chuỗi lọc-biến đổi rõ ràng bằng Stream cũng hợp lý. Chọn cấu trúc khiến **ý định và hành vi** dễ nhìn thấy nhất.
