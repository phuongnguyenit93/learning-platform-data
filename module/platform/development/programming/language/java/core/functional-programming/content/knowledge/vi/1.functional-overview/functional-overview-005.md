# Java hỗ trợ lập trình theo phong cách hàm qua những cơ chế nào?

Java là ngôn ngữ đa mô hình: lập trình hướng đối tượng và lập trình mệnh lệnh vẫn là nền tảng, nhưng từ Java 8, Java cung cấp nhiều cơ chế để biểu diễn **hành vi như dữ liệu**, truyền hành vi vào phương thức và xử lý tập dữ liệu theo các phép biến đổi. Đây là **lập trình theo phong cách hàm** (functional programming style), không có nghĩa Java trở thành ngôn ngữ thuần hàm.

## 1. Ý tưởng cốt lõi: mô tả phép biến đổi thay vì từng bước điều khiển

Trong cách viết mệnh lệnh, ta thường tạo danh sách kết quả, lặp qua dữ liệu, kiểm tra điều kiện rồi thêm từng phần tử. Với phong cách hàm, ta mô tả một chuỗi phép toán như **lọc → biến đổi → tổng hợp**. Mỗi phép toán nhận một hàm hoặc hành vi đã được biểu diễn bằng một đối tượng phù hợp.

Ví dụ về ý định “lấy tên nhân viên Backend có lương từ 25 trở lên, theo thứ tự tên”:

~~~java
List<String> names = employees.stream()
    .filter(e -> e.team().equals("Backend") && e.salary() >= 25)
    .map(Employee::name)
    .sorted()
    .toList();
~~~

Đây là **đoạn minh họa**; lớp Employee và biến employees được định nghĩa trong chương trình chạy hoàn chỉnh ở phần 8. Các bước filter, map, sorted đọc gần với yêu cầu nghiệp vụ, trong khi cơ chế duyệt và tích lũy được thư viện Stream thực hiện.

Một hàm *thuần* (pure function) trả cùng kết quả cho cùng đầu vào và không tạo tác dụng phụ quan sát được bên ngoài. Java không bắt buộc lambda phải thuần; người viết phải chủ động ưu tiên phép biến đổi không phụ thuộc trạng thái thay đổi.

## 2. Functional interface: kiểu đại diện cho hành vi

**Functional interface** là interface có đúng **một phương thức trừu tượng** (Single Abstract Method – SAM). Kiểu này làm cầu nối để biểu diễn một hành vi dưới dạng giá trị có thể gán vào biến, truyền làm tham số hoặc trả về từ phương thức.

~~~java
@FunctionalInterface
interface Rule {
    boolean accepts(int value);
}
~~~

Một đối tượng Rule thực thi hành vi nhận số nguyên và trả về true/false. Annotation @FunctionalInterface không bắt buộc, nhưng giúp trình biên dịch bắt lỗi khi interface vô tình có thêm phương thức trừu tượng thứ hai. Interface vẫn có thể khai báo nhiều phương thức default, static hoặc private; các phương thức tương ứng chữ ký public của Object không tính vào số phương thức trừu tượng của SAM.

Ví dụ sử dụng một functional interface tự định nghĩa:

~~~java
Rule positive = n -> n > 0;
System.out.println(positive.accepts(3));  // true
~~~

Hai đoạn trên có thể đặt cùng cấp trong một tệp Java hợp lệ, nhưng là **ví dụ ngắn**, không phải chương trình độc lập có main. Các lambda tương tự cũng dùng được với interface tiêu chuẩn có sẵn trong java.util.function.

Functional interface vẫn tuân theo hệ kiểu Java. Java không có cú pháp “kiểu hàm tự do” tương đương trực tiếp với mọi chữ ký hàm: lambda cần một **target type** là functional interface mà trình biên dịch có thể xác định từ phép gán, tham số hoặc kiểu trả về.

## 3. Lambda expression: viết hành vi ngắn gọn

**Lambda** diễn tả phần cài đặt của phương thức SAM mà không phải khai báo một lớp ẩn danh dài dòng.

- Một tham số, biểu thức đơn: n -> n * n.
- Nhiều tham số: (a, b) -> a + b.
- Thân khối: n -> { int square = n * n; return square; }.
- Không tham số: () -> "ready".

Trình biên dịch suy luận kiểu tham số từ target type khi có đủ ngữ cảnh:

~~~java
java.util.function.IntUnaryOperator square = n -> n * n;
java.util.function.BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
java.util.function.Supplier<String> ready = () -> "ready";
~~~

Lambda có thể **capture** biến cục bộ bên ngoài nếu biến đó là final hoặc *effectively final* (chỉ được gán một lần). Ví dụ:

~~~java
int minimum = 10;
java.util.function.IntPredicate isBig = n -> n > minimum;
~~~

Không thể gán lại minimum sau đó rồi tiếp tục dùng nó trong lambda, vì sẽ gây lỗi biên dịch. Tuy nhiên, effectively final **không bảo đảm đối tượng được capture là bất biến**: lambda vẫn có thể thay đổi nội dung của một List hoặc thuộc tính của đối tượng. Việc sửa trạng thái chia sẻ như vậy dễ gây lỗi khi có nhiều luồng.

Lambda không tạo một phạm vi this mới như anonymous class: this trong lambda trỏ tới đối tượng bao ngoài (nếu có). Ngoài ra, lambda không tự động chuyển checked exception thành unchecked exception; chữ ký SAM vẫn quyết định ngoại lệ checked nào được khai báo hoặc phải xử lý.

## 4. Method reference: tái sử dụng phương thức có sẵn

**Method reference** là cú pháp ngắn cho một lambda chủ yếu gọi lại phương thức hoặc constructor khác. Các dạng thường dùng:

| Dạng | Ví dụ | Ý nghĩa gần tương đương |
| --- | --- | --- |
| Static method | Integer::parseInt | s -> Integer.parseInt(s) |
| Instance method của đối tượng cụ thể | System.out::println | x -> System.out.println(x) |
| Instance method của đối tượng nhận vào | String::trim | s -> s.trim() |
| Constructor | ArrayList::new | () -> new ArrayList<>() |

Ví dụ:

~~~java
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.Function<String, String> trim = String::trim;
java.util.function.Supplier<java.util.ArrayList<String>> newList =
    java.util.ArrayList::new;
~~~

Method reference **không làm thay đổi hành vi** so với lambda tương ứng; dùng khi giúp mã rõ hơn. Chữ ký phương thức được tham chiếu phải tương thích với SAM, kể cả kiểu tham số, kiểu trả về và ngoại lệ. Với phương thức quá tải, target type giúp trình biên dịch chọn overload phù hợp.

## 5. java.util.function: các kiểu hàm tiêu chuẩn và phép kết hợp

Thay vì tự khai báo một interface cho mọi tác vụ, Java cung cấp các kiểu chức năng thường dùng:

| Interface | Vai trò | Phương thức SAM |
| --- | --- | --- |
| Predicate<T> | Kiểm tra điều kiện T → boolean | test(T) |
| Function<T,R> | Biến đổi T → R | apply(T) |
| Consumer<T> | Nhận T và thực hiện hành động, không trả kết quả | accept(T) |
| Supplier<T> | Cung cấp một giá trị T, không có đầu vào | get() |
| UnaryOperator<T> | Biến đổi T → T | apply(T) |
| BinaryOperator<T> | Kết hợp hai T thành một T | apply(T,T) |
| BiFunction<T,U,R> | Nhận hai giá trị, trả R | apply(T,U) |

Các phiên bản chuyên biệt cho kiểu nguyên thủy, như IntPredicate, IntFunction, IntUnaryOperator, ToIntFunction hoặc IntStream, giúp tránh boxing/unboxing không cần thiết trong nhiều trường hợp.

Điểm mạnh không chỉ nằm ở việc truyền lambda mà còn ở **kết hợp hàm**:

~~~java
java.util.function.Predicate<Integer> positive = n -> n > 0;
java.util.function.Predicate<Integer> even = n -> n % 2 == 0;
java.util.function.Predicate<Integer> positiveEven = positive.and(even);

java.util.function.Function<String, String> trim = String::trim;
java.util.function.Function<String, Integer> length = String::length;
java.util.function.Function<String, Integer> trimmedLength = trim.andThen(length);

System.out.println(positiveEven.test(12));   // true
System.out.println(trimmedLength.apply(" hi ")); // 2
~~~

Predicate có and, or, negate; Function có compose (áp dụng hàm trước) và andThen (áp dụng hàm sau). Đây là nền tảng xây dựng quy tắc nhỏ, kiểm thử được rồi ghép thành xử lý phức tạp, tránh nhồi mọi điều kiện vào một lambda dài.

Lưu ý: Consumer thường biểu diễn **tác dụng phụ** (ghi log, cập nhật trạng thái, gửi sự kiện). Nó hữu ích nhưng không phải ví dụ điển hình của hàm thuần; cần phân biệt sử dụng callback với thực hành lập trình thuần hàm.

## 6. Stream API: pipeline xử lý dữ liệu khai báo

**Stream** trong java.util.stream hỗ trợ xây chuỗi phép toán trên nguồn dữ liệu như Collection, mảng hoặc generator:

1. **Nguồn**: list.stream(), Arrays.stream(array), Stream.of(...), IntStream.range(...).
2. **Phép toán trung gian (intermediate)**: filter, map, flatMap, distinct, sorted, limit, peek. Phần lớn trả về một Stream mới.
3. **Phép toán kết thúc (terminal)**: toList, collect, reduce, count, findFirst, anyMatch, sum trên stream số nguyên, forEach. Phép toán kết thúc kích hoạt quá trình xử lý.

Ví dụ:

~~~java
long count = java.util.stream.Stream.of("Java", "Kotlin", "Go", "Java")
    .filter(s -> s.length() >= 4)
    .distinct()
    .count();
System.out.println(count); // 2
~~~

**Đánh giá lười (lazy evaluation):** các phép trung gian như filter hoặc map thường chưa chạy ngay lúc khai báo. Chúng được thực thi khi có terminal operation; terminal như findFirst hoặc anyMatch có thể kết thúc sớm. Không nên phụ thuộc vào số lần hay thứ tự callback được gọi để gây tác dụng phụ, vì thư viện được phép tối ưu pipeline theo hợp đồng API.

**map so với flatMap:** map biến mỗi phần tử thành một kết quả; flatMap biến mỗi phần tử thành một luồng rồi trải phẳng các luồng đó. Ví dụ một List<List<String>> có thể dùng flatMap(List::stream) để thành Stream<String>.

**reduce và collect:** reduce hợp với phép gộp bằng hàm kết hợp (như cộng, nhân, tìm max); collect dùng mutable reduction theo bộ gom như Collectors.groupingBy, joining, toMap. Khi dùng reduce trên stream song song, hàm tích lũy/kết hợp cần phù hợp với tính kết hợp, giá trị đơn vị và không can thiệp trạng thái chung.

**Stream không phải Collection:** Stream thường không lưu dữ liệu; nó mô tả cách duyệt, mỗi instance chỉ dùng cho một pipeline kết thúc. Không được chạy terminal operation thứ hai trên cùng stream đã tiêu thụ. Stream cũng không tự động sửa Collection gốc. Từ Java 16, Stream.toList() trả một List **không thể chỉnh sửa** (unmodifiable); đừng mặc định kết quả Collectors.toList() có cùng hợp đồng về khả năng chỉnh sửa.

**Thứ tự và song song:** sorted và findFirst có ngữ nghĩa phụ thuộc encounter order nếu nguồn có thứ tự. Chạy parallelStream() không tự động nhanh hơn; chi phí chia tác vụ, tính kết hợp, nguồn dữ liệu, tác dụng phụ và thứ tự đều ảnh hưởng hiệu năng. Với xử lý đơn giản hoặc tập nhỏ, luồng tuần tự thường dễ hiểu hơn.

## 7. Optional, Comparator và các API nhận hàm

**Optional<T>** biểu diễn khả năng có hoặc không có giá trị, đồng thời hỗ trợ map, flatMap, filter, orElseGet, ifPresent. Nó giúp mô tả bước xử lý khi thiếu kết quả rõ ràng hơn một chuỗi kiểm tra null thủ công.

~~~java
java.util.Optional<String> first = java.util.List.of("An", "Binh").stream()
    .filter(s -> s.startsWith("C"))
    .findFirst();
System.out.println(first.orElse("Không có")); // Không có
~~~

Optional không bảo đảm mọi API đều hết null: giá trị đầu vào vẫn có thể null, Optional.get() trên giá trị rỗng ném NoSuchElementException, và không nên tự động dùng Optional cho mọi field, parameter hoặc Collection.

**Comparator** có thể tạo bằng lambda, method reference và kết hợp thứ tự so sánh:

~~~java
java.util.Comparator<String> byLengthThenName =
    java.util.Comparator.comparingInt(String::length)
        .thenComparing(java.util.Comparator.naturalOrder());
~~~

Các API khác cũng dùng functional interface để nhận hành vi như Map.computeIfAbsent, Collection.removeIf, Iterable.forEach, CompletableFuture.thenApply và thenCompose. Với CompletableFuture, thenApply biến đổi kết quả bất đồng bộ; thenCompose ghép các tác vụ trả về CompletableFuture mà không tạo lớp Future lồng nhau. Đây là ứng dụng rộng hơn của việc truyền và kết hợp hàm, không đồng nghĩa mọi callback đều thuần hàm.

**Default method** trên interface giúp bổ sung các phép kết hợp như Predicate.and hoặc Comparator.thenComparing mà vẫn giữ giao diện chức năng có một phương thức trừu tượng. Các tính năng Java hiện đại như record hoặc List.of hỗ trợ thiết kế dữ liệu ít biến đổi, dù bản thân chúng không phải điều kiện bắt buộc để viết lambda hay Stream.

## 8. Ví dụ hoàn chỉnh chạy trên Java 17+

Chương trình sau dùng record cho dữ liệu, Predicate để tạo điều kiện, Function để tạo phép biến đổi, method reference, Stream, Collectors và Optional.

Tạo tệp **FunctionalStyleDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class FunctionalStyleDemo {
    record Employee(String name, String team, int salary) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("An", "Backend", 30),
            new Employee("Binh", "Frontend", 22),
            new Employee("Chi", "Backend", 40),
            new Employee("Dung", "Backend", 18)
        );

        Predicate<Employee> isBackend =
            e -> e.team().equals("Backend");
        Predicate<Employee> salaryAtLeast25 =
            e -> e.salary() >= 25;
        Function<Employee, String> describe =
            e -> e.name() + ":" + e.salary();

        List<String> selected = employees.stream()
            .filter(isBackend.and(salaryAtLeast25))
            .sorted(Comparator.comparing(Employee::name))
            .map(describe)
            .toList();
        System.out.println(selected);

        int backendTotal = employees.stream()
            .filter(isBackend)
            .mapToInt(Employee::salary)
            .sum();
        System.out.println(backendTotal);

        Map<String, Long> byTeam = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::team,
                TreeMap::new,
                Collectors.counting()
            ));
        System.out.println(byTeam);

        Optional<String> maybeMai = employees.stream()
            .filter(e -> e.name().equals("Mai"))
            .map(Employee::name)
            .findFirst();
        System.out.println(maybeMai.orElse("Không tìm thấy"));

        Function<String, String> trim = String::trim;
        Function<String, String> lower = String::toLowerCase;
        System.out.println(trim.andThen(lower).apply("  JAVA  "));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac FunctionalStyleDemo.java
java FunctionalStyleDemo
~~~

Stdout chính xác:

~~~text
[An:30, Chi:40]
88
{Backend=3, Frontend=1}
Không tìm thấy
java
~~~

Giải thích:

- Bộ lọc isBackend.and(salaryAtLeast25) chọn An và Chi. Comparator.comparing sắp xếp theo tên; map(describe) biến đối tượng Employee thành chuỗi.
- mapToInt + sum cộng 30 + 40 + 18 = 88 cho toàn bộ Backend, không áp dụng điều kiện mức lương từ phép lọc trước đó.
- groupingBy với TreeMap::new tạo nhóm theo team và in khóa theo thứ tự từ điển; vì vậy Backend xuất hiện trước Frontend.
- findFirst trả Optional.empty khi không có Mai; orElse cấp chuỗi dự phòng.
- trim.andThen(lower) cắt khoảng trắng trước rồi viết thường; các Function không cần trực tiếp sửa chuỗi ban đầu.

Để thay đổi nghiệp vụ, có thể thêm Predicate khác, thay Function hoặc đổi Collector mà vẫn giữ được cấu trúc pipeline.

## 9. Nguyên tắc dùng đúng và lỗi thường gặp

**Ưu tiên hàm ít tác dụng phụ.** Các thao tác trong map/filter lý tưởng chỉ dùng tham số đầu vào và trả kết quả. Tránh tăng biến đếm ngoài, thêm vào ArrayList chung hay thay đổi đối tượng trong callback, nhất là khi pipeline chạy song song. Dùng các phép kết thúc như count, reduce, collect để tổng hợp kết quả.

**Ưu tiên bất biến khi hợp lý.** List.of(...) và Stream.toList() tạo danh sách không cho phép thay đổi cấu trúc. Record giúp xác định dữ liệu gọn và các component là final, nhưng record chỉ bảo đảm *bất biến nông*: component tham chiếu đến một List có thể sửa thì nội dung List vẫn có thể thay đổi.

**Không dùng Stream chỉ để thay vòng lặp.** Vòng for vẫn phù hợp khi có điều khiển luồng phức tạp, cần break/continue rõ ràng, xử lý tác dụng phụ theo thứ tự hoặc debug từng bước. Pipeline nhiều tầng, lambda quá dài, hoặc lồng Stream không cần thiết có thể kém dễ đọc hơn vòng lặp đơn giản.

**Không dùng peek như bước xử lý nghiệp vụ.** peek chủ yếu phục vụ quan sát/debug; callback có thể không được gọi như kỳ vọng do đặc tính lazy và tối ưu. Khi muốn tạo dữ liệu mới, dùng map; khi muốn tích lũy, dùng collector phù hợp.

**Không tái sử dụng Stream.** Sau count, collect hoặc toList, cần lấy Stream mới từ nguồn nếu muốn xử lý tiếp.

**Xử lý null và checked exception có chủ đích.** Method reference như Integer::parseInt vẫn có thể ném NumberFormatException nếu dữ liệu không hợp lệ. Stream không tự bắt ngoại lệ, lambda không xóa yêu cầu xử lý checked exception. Đặt logic xác thực hoặc chuyển đổi lỗi rõ ràng tại ranh giới phù hợp.

**Giữ đúng hợp đồng khi chạy song song.** Tránh mutable shared state, đảm bảo hàm reduce có tính kết hợp, nhớ rằng forEach trên parallel stream không bảo đảm thứ tự; dùng forEachOrdered nếu thứ tự quan trọng, đồng thời cân nhắc chi phí hiệu năng.

**Không nhầm phong cách hàm với tính thuần hàm.** Java vẫn cho phép mutable object, null, tác dụng phụ, exception và vòng lặp. Functional interface, lambda và Stream là công cụ để giảm mã lặp, tách hành vi, tăng khả năng kết hợp và kiểm thử; độ an toàn phụ thuộc thiết kế của người dùng chúng.

## 10. Ghi nhớ và tự kiểm tra

Các cơ chế Java hỗ trợ trực tiếp nhất là: **functional interface (SAM)** tạo kiểu cho hành vi; **lambda** và **method reference** cung cấp hành vi; **java.util.function** định nghĩa các dạng hàm và phép kết hợp; **Stream/Collectors** xử lý dữ liệu khai báo; **Optional, Comparator và các API nhận callback** cho phép tái sử dụng phong cách này trong nhiều ngữ cảnh. Immutable data và default method giúp các thiết kế này dễ phối hợp hơn.

Tự kiểm tra bằng ba câu hỏi: (1) Khi nào một interface được xem là functional interface, và vì sao lambda cần target type? (2) Vì sao một Stream đã gọi count không thể tiếp tục gọi map trên chính instance đó? (3) Vì sao thêm phần tử vào một ArrayList dùng chung trong parallelStream().forEach(...) có thể cho kết quả sai? Trả lời được ba câu hỏi này giúp phân biệt **cú pháp hàm** với **thiết kế chương trình an toàn theo phong cách hàm**.