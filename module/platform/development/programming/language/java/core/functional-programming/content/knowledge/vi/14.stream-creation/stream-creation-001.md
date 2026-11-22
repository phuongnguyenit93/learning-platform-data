# Tạo Stream từ Collection.stream() và parallelStream() trong Java

## 1. Vì sao Collection có thể tạo Stream?

Khi đã có một tập dữ liệu trong Java, chẳng hạn `List<Order>`, `Set<String>` hoặc `Queue<Integer>`, ta thường muốn lọc, chuyển đổi, tổng hợp các phần tử mà không tự viết vòng lặp cho từng bước. **Java Stream API** cho phép mô tả chuỗi xử lý dữ liệu theo kiểu khai báo.

Hai phương thức trên interface `java.util.Collection<E>` là điểm bắt đầu phổ biến:

~~~java
Stream<E> sequential = collection.stream();
Stream<E> possiblyParallel = collection.parallelStream();
~~~

Đây là **cú pháp minh họa**, trong đó `collection` đã được khai báo là một `Collection<E>` và cần import `java.util.stream.Stream`. Chúng đều trả về một đối tượng Stream có nguồn là collection, nhưng khác nhau về **chế độ thực thi được yêu cầu**:

- `stream()` trả một **Stream tuần tự** (*sequential stream*).
- `parallelStream()` trả một **Stream có thể xử lý song song** (*possibly parallel stream*). Với các collection chuẩn thông dụng như `List.of(...)` hoặc `ArrayList` trong JDK 17, stream thu được ở chế độ parallel; tuy nhiên hợp đồng `Collection.parallelStream()` **cho phép** implementation trả về stream tuần tự. Không coi tên phương thức là cam kết chắc chắn về số thread hay mức tăng tốc.

Điểm cần nhớ: **Collection giữ dữ liệu, Stream mô tả và thực thi quá trình xử lý dữ liệu đó khi cần**. Tạo Stream không tự biến collection thành danh sách kết quả mới và thường chưa thực hiện các phép `filter` hoặc `map` ngay lập tức.

## 2. Tạo Stream tuần tự bằng Collection.stream()

### 2.1. Ví dụ cơ bản với List

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi");
List<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList();
~~~

Đoạn này là **mã minh họa trong một phương thức**. Từ một `List<String>`, `names.stream()` tạo `Stream<String>` để kết nối các bước:

1. `filter(...)` giữ những tên có độ dài từ 3 trở lên.
2. `map(...)` chuyển từng tên phù hợp thành chữ hoa.
3. `toList()` là thao tác kết thúc (*terminal operation*) để tạo danh sách kết quả.

Ở đây collection nguồn `names` không bị thay đổi chỉ vì pipeline đã chạy. Các phương thức `filter` và `map` trả về Stream trung gian, không thêm/xóa phần tử trong nguồn theo thiết kế API. Tuy vậy, lambda của người dùng **có thể** chứa tác dụng phụ; do đó cần phân biệt hành vi của Stream API với hành vi do callback tự viết.

### 2.2. Các dạng Collection khác

Không chỉ `List`, mọi đối tượng triển khai `Collection<E>` đều cung cấp cách gọi tương ứng, bao gồm nhiều kiểu `Set` và `Queue`.

~~~java
Set<Integer> distinctNumbers = Set.of(4, 1, 3, 2);
long evenCount = distinctNumbers.stream()
        .filter(number -> number % 2 == 0)
        .count();
~~~

Đây là **đoạn minh họa** trong một phương thức, cần import `java.util.Set`. `evenCount` bằng 2 vì có hai giá trị chẵn 2 và 4.

**Lưu ý về thứ tự:** không thể suy ra mọi `Collection` đều có *encounter order* giống `List`. `List` thường có thứ tự theo chỉ số; `LinkedHashSet` duy trì thứ tự lặp; còn `HashSet` không bảo đảm thứ tự lặp có ý nghĩa cố định theo hợp đồng. Một pipeline dựa vào thứ tự cần kiểm tra loại nguồn và thao tác trước khi trông đợi thứ tự đầu ra.

### 2.3. Map không trực tiếp extends Collection

`Map<K,V>` là một abstraction khác, **không** triển khai `Collection`. Vì thế không dùng `map.stream()` với một `Map` chuẩn. Thay vào đó, chọn cách nhìn dữ liệu phù hợp:

~~~java
Map<String, Integer> scores = Map.of("An", 8, "Chi", 9);

long highScoreCount = scores.values().stream()
        .filter(score -> score >= 9)
        .count();

List<String> highScoreNames = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 9)
        .map(Map.Entry::getKey)
        .sorted()
        .toList();
~~~

Đoạn minh họa này cần import `java.util.Map` và `java.util.List`. `scores.values()` trả một Collection của giá trị, `scores.entrySet()` trả Set của các entry, còn `scores.keySet()` là Set của khóa. Với dữ liệu đã cho, `highScoreCount` bằng 1 và `highScoreNames` bằng `[Chi]`. Thao tác `sorted()` giúp kết quả có thứ tự rõ ràng thay vì dựa vào thứ tự lặp của `Map.of`.

## 3. Tạo Stream có chế độ song song bằng Collection.parallelStream()

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

int total = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Đoạn này là **mã minh họa trong phương thức**, cần import `java.util.List`. Kết quả là 15. Việc cộng các số là ví dụ đơn giản, vì phép cộng nguyên phù hợp với việc chia nguồn thành các phần rồi kết hợp kết quả.

Khi Stream ở chế độ parallel và pipeline được đánh giá song song, thư viện có thể **chia dữ liệu** thành những phần nhỏ, xử lý các phần độc lập rồi **gộp kết quả**. Bộ tách nguồn (*Spliterator*) đóng vai trò cung cấp/split phần tử. Chế độ parallel không đồng nghĩa “một thread cho mỗi phần tử”, cũng không bảo đảm chạy nhanh hơn.

Một biểu diễn khái niệm:

~~~text
Collection<Integer> [1, 2, 3, 4, 5]
             |
       parallelStream()
             |
       chia thành các phần
        /        |       \
    [1,2]      [3,4]     [5]
       \         |        /
         tính và kết hợp
               |
             sum()
               |
              15
~~~

Sơ đồ minh họa **ý tưởng chia và gộp**, không phải lịch phân chia/thread được JDK bảo đảm. Cách phân mảnh, thứ tự xử lý và mức parallelism phụ thuộc implementation, kích thước nguồn, chi phí từng phép toán và môi trường thực thi.

### 3.1. Khi nào callback thực thi?

Các phép `filter`, `map`, `mapToInt`, `sorted` thường là **intermediate operations**. Chúng xây dựng pipeline mà không tự bắt buộc đánh giá mọi phần tử tại thời điểm khai báo.

~~~java
Stream<Integer> pipeline = numbers.parallelStream()
        .filter(n -> n > 2)
        .map(n -> n * 10);

// Chỉ ở bước terminal mới yêu cầu kết quả:
List<Integer> result = pipeline.toList();
~~~

Đây là đoạn minh họa, cần import `java.util.stream.Stream` và có biến `numbers` kiểu collection phù hợp. Với List gồm 1 đến 5, kết quả là `[30, 40, 50]`.

Không nên đoán số lần callback được gọi chỉ dựa trên số phần tử nguồn: một số terminal operation có thể dừng sớm hoặc được tối ưu, và các side effect trong pipeline không phải là tín hiệu đáng tin để “đếm số phần tử đã xử lý”.

### 3.2. Kiểm tra chế độ với isParallel()

~~~java
Stream<Integer> seq = numbers.stream();
Stream<Integer> par = numbers.parallelStream();

System.out.println(seq.isParallel());
System.out.println(par.isParallel());
~~~

Đoạn này giả định `numbers` là `List<Integer>` chuẩn hỗ trợ parallel stream (như `List.of(...)`), và đã import `java.util.stream.Stream`. Trong môi trường ví dụ Java 17, kết quả lần lượt là `false` và `true`.

`isParallel()` cho biết **chế độ của Stream**, không phải số thread thực sự đang chạy lúc kiểm tra. Việc tạo Stream, hỏi chế độ rồi xử lý bằng terminal operation là hợp lệ. Tuy nhiên, sau khi Stream đã bị tiêu thụ hoặc đóng, không được tiếp tục xây dựng pipeline mới từ cùng instance.

## 4. stream() và parallelStream(): giống nhau ở đâu, khác nhau ở đâu?

| Tiêu chí | `collection.stream()` | `collection.parallelStream()` |
| --- | --- | --- |
| Chế độ khởi đầu | Tuần tự | Có thể song song, phụ thuộc implementation |
| Kiểu trả về | `Stream<E>` | `Stream<E>` |
| Nguồn phần tử | Collection đang có | Cùng Collection đang có |
| Các phép như `filter`, `map`, `reduce` | Dùng được | Dùng được |
| Thứ tự gặp phần tử (*encounter order*) | Tùy nguồn | Vẫn tùy nguồn; xử lý có thể không theo thứ tự |
| Callback có được phép sửa nguồn tùy ý? | Không | Không |
| Chi phí phối hợp công việc | Thường ít hơn | Có thể thêm split, scheduling, synchronization/merge |
| Khi nào ưu tiên? | Mặc định an toàn, dễ đọc | Khi tác vụ thích hợp, đủ lớn và đã đo hiệu quả |

**Không có sự khác nhau về “loại Stream” theo API trả về.** Một đối tượng `Stream<E>` có thể được đặt ở chế độ sequential hoặc parallel; phần lớn thao tác trung gian vẫn giống nhau về mặt khai báo.

Ngoài cách tạo trực tiếp từ collection, có thể đổi chế độ của pipeline bằng `parallel()` hoặc `sequential()`:

~~~java
List<Integer> a = numbers.stream().parallel()
        .map(x -> x * 2).toList();

List<Integer> b = numbers.parallelStream().sequential()
        .map(x -> x * 2).toList();
~~~

Hai đoạn đều minh họa cùng phép biến đổi với kết quả giống nhau đối với dữ liệu đầu vào là List ổn định. Các phương thức `parallel()` và `sequential()` thay đổi chế độ của pipeline. Không nên dựa vào việc trộn liên tục nhiều lệnh đổi chế độ để mong những đoạn khác nhau của cùng pipeline dùng các chế độ độc lập: chế độ thực thi là đặc tính của pipeline được đánh giá, không phải cam kết rằng mỗi đoạn sẽ có thread riêng.

## 5. Một chương trình Java 17 hoàn chỉnh

Tạo tệp **CollectionStreamsDemo.java**. Chương trình dùng Collection trong các tình huống cụ thể:

- Tạo Stream tuần tự và parallel từ cùng `List<Integer>`.
- Xác minh `isParallel()` trên các Stream được tạo.
- Tính tổng bằng tuần tự/song song.
- Biến đổi và lọc mà giữ thứ tự kết quả khi thu thập về List có encounter order.
- Gom nhóm từ parallel stream bằng collector an toàn.
- Dùng `findFirst()` để lấy phần tử đầu theo thứ tự nguồn.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionStreamsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);
        Stream<Integer> seq = numbers.stream();
        Stream<Integer> par = numbers.parallelStream();
        System.out.println("seq.isParallel=" + seq.isParallel());
        System.out.println("par.isParallel=" + par.isParallel());

        int seqSum = seq.mapToInt(Integer::intValue).sum();
        int parSum = par.mapToInt(Integer::intValue).sum();
        System.out.println("seq sum=" + seqSum);
        System.out.println("par sum=" + parSum);

        List<Integer> squares = numbers.parallelStream()
                .map(n -> n * n)
                .toList();
        System.out.println("squares=" + squares);

        List<String> names = List.of("an", "binh", "chi", "dung");
        List<String> upper = names.parallelStream()
                .map(name -> name.toUpperCase(Locale.ROOT))
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("upper=" + upper);

        List<String> words = List.of("java", "stream", "java", "parallel");
        Map<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        TreeMap::new,
                        Collectors.counting()));
        System.out.println("counts=" + counts);
        System.out.println("first=" +
                numbers.parallelStream().findFirst().orElseThrow());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc phiên bản JDK cao hơn hỗ trợ đích 17:

~~~bash
javac --release 17 CollectionStreamsDemo.java
java CollectionStreamsDemo
~~~

Stdout đã kiểm chứng trực tiếp:

~~~text
seq.isParallel=false
par.isParallel=true
seq sum=15
par sum=15
squares=[1, 4, 9, 16, 25]
upper=[BINH, CHI, DUNG]
counts={java=2, parallel=1, stream=1}
first=1
~~~

### 5.1. Giải thích từng kết quả

1. `numbers.stream()` có chế độ tuần tự, `numbers.parallelStream()` có chế độ parallel trong implementation dùng ở ví dụ. Vì thế `isParallel()` trả tương ứng `false` và `true`. Không suy ra `parallelStream()` buộc phải tạo nhiều thread cho năm phần tử nhỏ này.
2. Hai pipeline cộng `1+2+3+4+5=15`. Chúng không cần bảo toàn thứ tự thực thi từng phần tử để bảo toàn kết quả phép cộng phù hợp.
3. `squares` là `[1,4,9,16,25]`: `List.of` có thứ tự gặp, `map` giữ encounter order và `toList()` trả các phần tử theo thứ tự đó. Điều này không có nghĩa callback `map` đã chạy lần lượt 1,2,3,4,5 khi pipeline parallel.
4. Danh sách tên nguồn là `["an","binh","chi","dung"]`. `map` chuyển chữ hoa; `filter` loại `AN` có độ dài 2; `toList()` đưa ra `[BINH,CHI,DUNG]` theo thứ tự gặp.
5. `groupingBy` được cung cấp một `TreeMap` làm nơi lưu kết quả nhóm, nên biểu diễn map theo khóa theo thứ tự tự nhiên: `java`, `parallel`, `stream`. `Collectors.counting()` đếm số lần mỗi chuỗi xuất hiện. Collector được API thực thi theo cơ chế thu thập thích hợp; code người dùng không cần tự sửa một `HashMap` dùng chung từ nhiều thread.
6. `findFirst()` trên nguồn List có encounter order trả phần tử đầu là 1, dù pipeline có chế độ parallel. Đổi sang `findAny()` sẽ không có bảo đảm lựa chọn phần tử đầu theo thứ tự đó.

Cách viết `words.parallelStream().collect(Collectors.groupingBy(...))` là ví dụ **thu thập có kiểm soát**, khác với việc mỗi callback tự sửa một `Map` mutable dùng chung.

## 6. Tính thứ tự trong parallel stream

Một trong những nhầm lẫn phổ biến nhất là: “parallelStream sẽ luôn đảo lộn thứ tự kết quả”. Thực tế phải phân biệt ba yếu tố:

- **Encounter order**: nguồn/pipeline có thứ tự gặp phần tử được định nghĩa hay không?
- **Thứ tự chạy callback**: phần tử nào được xử lý trước trên thread nào?
- **Thứ tự của kết quả**: terminal operation có cam kết thứ tự nào không?

Với một `List` có thứ tự, nhiều thao tác như `filter` và `map` duy trì thứ tự gặp về mặt logic. `Stream.toList()` trả danh sách theo encounter order **nếu Stream có encounter order**, kể cả khi xử lý song song. Tuy nhiên các callback có thể chạy ở thứ tự và trên thread khác nhau.

| Thao tác | Điểm cần nhớ |
| --- | --- |
| `map`, `filter` | Kết quả logic giữ encounter order của nguồn có thứ tự, nhưng không cam kết callback chạy theo đúng thứ tự thời gian |
| `toList()` | Kết quả theo encounter order nếu Stream có thứ tự; danh sách trả về không cho phép sửa cấu trúc |
| `findFirst()` | Lấy phần tử đầu theo encounter order nếu có, có thể có chi phí giữ thứ tự |
| `findAny()` | Có thể trả bất kỳ phần tử nào phù hợp; thích hợp khi không cần vị trí đầu |
| `forEach(...)` | Trong parallel stream không bảo đảm thứ tự thực hiện |
| `forEachOrdered(...)` | Bảo đảm các action theo encounter order nếu có, nhưng có thể giảm lợi ích song song |
| `unordered()` | Gỡ ràng buộc encounter order để một số phép xử lý có cơ hội tối ưu; không phải tự xáo trộn dữ liệu |

Không đoán output cố định của `parallelStream().forEach(System.out::print)`: thứ tự được quan sát phụ thuộc lịch chạy. Nếu bài học yêu cầu output đáng tin, hãy dùng phép tổng hợp hoặc terminal operation có contract phù hợp.

**Lưu ý về performance:** các thao tác giữ thứ tự như `limit`, `skip`, `distinct` hoặc `findFirst` có thể phải phối hợp nhiều hơn khi chạy parallel trên nguồn có thứ tự. Đôi khi `unordered()` hợp lý nếu nghiệp vụ thực sự không cần thứ tự; không bỏ ràng buộc thứ tự chỉ vì muốn nhanh hơn khi thứ tự là yêu cầu.

## 7. Stream có phải bản sao của Collection không?

**Không nên coi `stream()`/`parallelStream()` là phép snapshot dữ liệu.** Stream thông thường tham chiếu nguồn và thực hiện phép duyệt khi terminal operation đánh giá pipeline. Nó không mặc định sao chép toàn bộ collection ngay lúc tạo.

Ví dụ:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
Stream<Integer> stream = numbers.stream();
~~~

Đây là đoạn minh họa cần import `java.util.ArrayList`, `java.util.List`, `java.util.stream.Stream`. Dòng tạo `stream` chưa tạo một `List<Integer>` kết quả độc lập.

### 7.1. Không sửa nguồn khi đang xử lý

Phần lớn các nguồn Stream yêu cầu callback **non-interfering**: không làm thay đổi nguồn đang được duyệt. Ví dụ dưới đây là **phản ví dụ, không nên chạy trong chương trình thực**:

~~~java
// SAI VỀ CÁCH SỬ DỤNG STREAM:
// List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
// numbers.stream().forEach(n -> numbers.add(n + 10));
~~~

Thay đổi cấu trúc collection khi đang duyệt có thể dẫn đến lỗi như `ConcurrentModificationException` hoặc hành vi không mong muốn, tùy loại nguồn và điều kiện chạy. Không có bảo đảm rằng mọi lần vi phạm đều bị phát hiện bằng exception.

Một cách hợp lý hơn khi cần danh sách mới:

~~~java
List<Integer> expanded = numbers.stream()
        .map(n -> n + 10)
        .toList();
~~~

Kết quả `expanded` không sửa cấu trúc nguồn, và có giá trị biến đổi của các phần tử theo pipeline. `Stream.toList()` trả về danh sách không cho phép sửa cấu trúc (không được gọi `add`, `remove`... để thay đổi danh sách đó). Nó **không bảo đảm các object phần tử đều bất biến sâu**.

### 7.2. Collection thay đổi giữa lúc tạo Stream và lúc tiêu thụ

Việc thay đổi nguồn trước hoặc trong khi tiêu thụ Stream chịu quy tắc binding/spliterator và đặc tính của từng collection. Một số nguồn có spliterator **late-binding**, một số khác có thiết kế concurrent hoặc snapshot riêng.

Vì vậy, không thể nói “mọi Stream đều nhìn thấy bản cập nhật mới nhất” hay “mọi Stream luôn nhìn thấy snapshot khi tạo”. Với logic cần dữ liệu ổn định, hãy thiết kế **snapshot có chủ đích**, khóa đồng bộ phù hợp, collection bất biến hoặc một nguồn có contract concurrent rõ ràng.

Trong phần lớn bài toán xử lý danh sách, lựa chọn dễ hiểu nhất là hoàn tất việc xây dựng dữ liệu nguồn trước, rồi tạo và tiêu thụ Stream mà không sửa nguồn đồng thời.

### 7.3. Stream thường chỉ tiêu thụ một lần

~~~java
Stream<Integer> once = numbers.stream();
long count = once.count();

// CỐ Ý KHÔNG HỢP LỆ KHI CHẠY:
// long second = once.count();
// Stream đã được tiêu thụ; tái sử dụng có thể gây IllegalStateException.
~~~

Đây là đoạn minh họa trong một phương thức. Nếu cần xử lý hai lần, **tạo hai Stream mới từ cùng collection**:

~~~java
long count = numbers.stream().count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
~~~

Không nên lưu một instance Stream đã tiêu thụ để dùng đi dùng lại như thể nó là một List.

## 8. Điều kiện để parallelStream thực sự phù hợp

Parallel stream có thể giúp khi công việc đủ lớn và có thể chia độc lập, nhưng cũng có chi phí phân chia/sắp lịch/phối hợp. Một quyết định hợp lý nên xem cả **dữ liệu**, **hàm xử lý**, **thao tác tổng hợp** và **môi trường chạy**.

### 8.1. Nguồn có thể tách hiệu quả

Các collection có cấu trúc truy cập/tách dữ liệu hiệu quả thường thuận lợi hơn những nguồn khó chia đều. Nguồn có kích thước biết trước và Spliterator phù hợp giúp hệ thống tổ chức công việc hiệu quả.

Ví dụ một `ArrayList` lớn có thể tách phạm vi phần tử theo chỉ số tương đối thuận tiện. Tuy nhiên, hiệu quả vẫn phụ thuộc chi phí xử lý và đặc điểm pipeline; không thể suy ra mọi `ArrayList.parallelStream()` đều nhanh hơn `stream()`.

### 8.2. Callback không có trạng thái chia sẻ khó kiểm soát

Một phép ánh xạ tương đối an toàn:

~~~java
List<Integer> squares = numbers.parallelStream()
        .map(value -> value * value)
        .toList();
~~~

Trong đoạn minh họa này, lambda chỉ dùng giá trị đầu vào và trả giá trị mới. Nó không sửa biến chia sẻ và do đó dễ lý giải khi chạy song song.

Phản ví dụ cần tránh:

~~~java
// KHÔNG AN TOÀN với parallel stream:
// List<Integer> shared = new ArrayList<>();
// numbers.parallelStream().forEach(shared::add);
~~~

`ArrayList` không bảo đảm thread-safe cho nhiều ghi đồng thời. Kết quả có thể bị mất phần tử hoặc lỗi; không dùng danh sách mutable chia sẻ để làm collector thủ công.

Cách đúng hơn để tạo kết quả:

~~~java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

Khi cần gom nhóm, thống kê hoặc map, dùng `collect` với collector thích hợp. Điều đó cho phép Stream framework phân chia và kết hợp dữ liệu theo hợp đồng Collector thay vì dựa vào mutation dùng chung.

### 8.3. Phép gộp phải thỏa hợp đồng reduction

Một parallel reduction cần phép kết hợp phù hợp, thường phải **associative** và có giá trị identity chính xác để kết quả không phụ thuộc cách phân nhóm.

~~~java
int total = numbers.parallelStream()
        .reduce(0, Integer::sum);
~~~

Với các số nguyên nhỏ trong bài này, phép cộng có phần tử trung tính 0 và có thể kết hợp, nên phép reduction phù hợp.

Không nên dùng phép trừ như một phép gộp tùy ý để mong có cùng kết quả tuần tự và song song:

~~~java
// KHÔNG THÍCH HỢP để giảm song song như một phép gộp kết hợp:
// int difference = numbers.parallelStream().reduce(0, (a, b) -> a - b);
~~~

Phép trừ không có tính kết hợp: `(a-b)-c` khác `a-(b-c)`. Kết quả có thể thay đổi khi phép tính được chia nhóm theo cách khác. Với các phép toán số thực, còn phải xem ảnh hưởng thứ tự cộng và sai số dấu phẩy động; không tự hứa kết quả bit-for-bit giống nhau trong mọi cấu hình.

### 8.4. Tác vụ có cần giữ thứ tự nghiêm ngặt không?

Nếu cần xử lý theo thứ tự để cập nhật một tài nguyên chung, parallel có thể không hợp hoặc tốn nhiều công đồng bộ. Nếu chỉ cần tổng hợp độc lập trên nhiều phần tử, parallel có thể phù hợp hơn.

Không nên dùng `parallelStream()` cho các callback vốn dựa vào thứ tự để cập nhật trạng thái, như cộng vào một biến mutable bên ngoài bằng `forEach`. Hãy đổi sang `reduce`, `mapToInt().sum()` hoặc collector tương ứng.

### 8.5. Hiệu năng phải đo bằng benchmark thích hợp

“Song song” không đồng nghĩa “nhanh hơn”. Với danh sách nhỏ hoặc thao tác rất rẻ, overhead có thể lớn hơn lợi ích. Tốc độ cũng chịu tác động của CPU, bộ nhớ/cache, GC, nguồn dữ liệu, contention và hệ thống đang chạy những tác vụ gì.

Ưu tiên:
1. Viết phiên bản tuần tự đúng, dễ kiểm thử.
2. Chứng minh pipeline đủ độc lập và reduction đáp ứng hợp đồng.
3. Benchmark bằng công cụ phù hợp như **JMH**, có warm-up, nhiều lần đo và dữ liệu đại diện.
4. Chỉ chọn parallel khi lợi ích đo được đủ ổn định và việc vận hành không bị ảnh hưởng bất lợi.

Không viết bài kiểm thử `System.currentTimeMillis()` một lần rồi kết luận tổng quát về hiệu năng.

## 9. Thread, ForkJoinPool và các giới hạn vận hành

Trong nhiều implementation JDK thông dụng, parallel stream sử dụng cơ chế fork/join để phân chia tác vụ và thường tận dụng tài nguyên kiểu `ForkJoinPool.commonPool()`. Tuy nhiên, **không nên biến chi tiết implementation đó thành hợp đồng rằng mọi callback phải chạy trong một pool/thread cố định**.

Một số điều không được mặc định:

- Không bảo đảm mỗi phần tử chạy trên một thread riêng.
- Không bảo đảm chỉ có một số thread chính xác cho mọi môi trường.
- Không bảo đảm `parallelStream()` nhanh hơn với thao tác I/O chặn như gọi HTTP hoặc đọc mạng.
- Không bảo đảm “bật parallel” là giải pháp thay thế thiết kế async, backpressure, timeout hay thread pool chuyên biệt.

Trong server phục vụ nhiều request, chạy parallel stream tùy tiện có thể cạnh tranh CPU với các request khác hoặc chặn tài nguyên dùng chung. Với thao tác I/O lâu, nhu cầu kiểm soát concurrency/timeout thường được thể hiện rõ hơn qua executor, tác vụ bất đồng bộ hoặc mô hình concurrency chuyên dụng.

**Tóm lại:** parallel stream thích hợp nhất cho những phép tính độc lập, đủ tốn CPU, không tác dụng phụ và có phép gom an toàn, chứ không phải cho mọi loại “công việc có nhiều phần tử”.

## 10. Phân biệt parallel stream và thread safety của dữ liệu

Một Stream ở chế độ parallel **không làm collection nguồn tự động thread-safe**, cũng không làm callback được gọi một cách tuần tự có kiểm soát.

Nếu nguồn là `ArrayList` mutable và các thread khác đang thêm/xóa phần tử trong lúc stream đang duyệt, việc dùng parallel không giải quyết vấn đề race condition. Nếu các phần tử là object mutable và nhiều callback sửa cùng object, tính nhất quán vẫn phụ thuộc vào cơ chế đồng bộ và thiết kế dữ liệu.

Tương tự, `Collections.synchronizedList(...)` không tự thay thế yêu cầu phối hợp khi duyệt bằng Stream trong lúc thread khác sửa collection. Cần tuân theo hợp đồng synchronization của loại collection và ngữ cảnh cụ thể, hoặc chuyển sang snapshot/collection concurrent với semantics phù hợp.

**Nguyên tắc dùng được ở cả hai chế độ:** nguồn nên ổn định trong quá trình traversal, các phép `map`/`filter` nên *stateless* và *non-interfering*, reduction/collector phải được lựa chọn theo yêu cầu tổng hợp.

## 11. Câu hỏi thường gặp và lỗi phổ biến

### 11.1. Gọi stream() hai lần có phải tạo bản sao dữ liệu hai lần?

Không. Mỗi lời gọi tạo một đối tượng Stream/pipeline mới có cùng nguồn logic. Tạo Stream không tự sao chép toàn bộ collection. Tuy nhiên, các terminal operation như `toList()` hoặc `toArray()` có thể cấp phát vùng chứa kết quả.

### 11.2. parallelStream() có bảo đảm thứ tự tương tự stream() không?

Phải tách **thứ tự logic của kết quả** với **thứ tự thời gian xử lý callback**. Từ List có encounter order, nhiều terminal operation như `toList()` giữ thứ tự kết quả; `forEach` song song không bảo đảm thứ tự callback.

### 11.3. Dùng parallelStream() cho một List gồm vài phần tử có lợi không?

Không thể kết luận trước. Với vài phần tử và thao tác rẻ, overhead thường đáng kể so với công việc; vì vậy nên dùng `stream()` làm mặc định và đo trước khi tối ưu.

### 11.4. HashSet.parallelStream().toList() có thứ tự ổn định không?

Không có bảo đảm về thứ tự gặp cho `HashSet` theo hợp đồng. Nếu cần một danh sách theo thứ tự xác định, áp dụng `sorted()` với các phần tử có thứ tự so sánh phù hợp hoặc chọn nguồn có encounter order mong muốn.

### 11.5. Nếu chạy Stream song song và kết quả tổng sai, có phải Java tự mất dữ liệu?

Không nên kết luận như vậy. Thường cần kiểm tra callback có side effect, biến dùng chung, phép reduction không associative, hoặc nguồn bị sửa đồng thời. Dùng collector/reduction đúng hợp đồng và dữ liệu ổn định trước khi nghi ngờ implementation.

### 11.6. Chuyển parallelStream().sequential() có tạo collection mới không?

Không. Nó đổi chế độ của pipeline Stream, không phải phép sao chép phần tử. Kết quả materialize chỉ được tạo khi một terminal operation yêu cầu.

### 11.7. Có bắt buộc import java.util.stream.Stream để gọi list.stream() không?

Không nếu chỉ gọi chuỗi trực tiếp như `list.stream().filter(...).toList()` và compiler biết kiểu trả về từ API. Cần import `java.util.stream.Stream` khi khai báo tên kiểu `Stream<T>` mà không dùng tên đầy đủ.

## 12. Checklist chọn stream() hay parallelStream()

Khi bắt đầu từ một `Collection<T>`, tự trả lời lần lượt:

1. **Tôi có cần một pipeline xử lý dữ liệu hay chỉ cần duyệt đơn giản?** Nếu chỉ là vòng lặp ngắn và rõ ràng, không bắt buộc dùng Stream.
2. **Nguồn có kích thước đáng kể và có thể chia việc hiệu quả không?** Nếu không, thử tuần tự trước.
3. **Lambda có stateless, non-interfering, không sửa biến chia sẻ không?** Nếu chưa, chỉnh thiết kế trước khi chạy parallel.
4. **Reduction/collector có kết hợp đúng và không phụ thuộc thứ tự thao tác không?** Nếu không, không dùng parallel kiểu tùy tiện.
5. **Tôi cần encounter order của kết quả không?** Nếu có, chọn operation giữ thứ tự và tính đến chi phí của nó.
6. **Có I/O, blocking, timeout, rate limit hoặc tài nguyên dùng chung không?** Nếu có, thiết kế cơ chế concurrency phù hợp thay vì coi parallel stream là lời giải mặc định.
7. **Đã đo hiệu năng với dữ liệu và môi trường đại diện chưa?** Chỉ tối ưu khi có bằng chứng.
8. **Tôi có vô tình tái dùng Stream sau terminal operation hoặc sửa Collection trong lúc traversal không?** Nếu có, cần thay đổi.

**Kết luận lựa chọn:** với hầu hết mã nghiệp vụ thông thường, `collection.stream()` là điểm bắt đầu đơn giản và dễ dự đoán hơn. `collection.parallelStream()` đáng cân nhắc khi công việc đủ lớn, chia được, ít phụ thuộc thứ tự, không chia sẻ trạng thái nguy hiểm và đã đo được lợi ích thực tế.

## 13. Bài tập tự kiểm tra

**Bài 1.** Với `List<Integer> values = List.of(2,4,6);`, `values.stream().mapToInt(Integer::intValue).sum()` trả gì? Chế độ mặc định là gì?

**Đáp án:** 12 và stream tuần tự.

**Bài 2.** Với `List<String> names = List.of("An","Bình","Chi");`, dùng `names.parallelStream().map(String::length).toList()` có bảo đảm danh sách kết quả theo thứ tự phần tử nguồn không?

**Đáp án:** Có, với List có encounter order và terminal operation `toList()`, danh sách đầu ra giữ encounter order; không suy ra callback chạy theo thứ tự thời gian.

**Bài 3.** Vì sao `new HashMap<...>().stream()` không hợp lệ?

**Đáp án:** `Map` không triển khai `Collection`. Hãy dùng `entrySet().stream()`, `keySet().stream()` hoặc `values().stream()` theo nhu cầu.

**Bài 4.** Nếu dùng `parallelStream().forEach(sharedList::add)` với `ArrayList` chung, vấn đề gì có thể xảy ra?

**Đáp án:** race condition và trạng thái không nhất quán vì ArrayList không thread-safe cho nhiều ghi đồng thời; dùng `toList()` hoặc collector phù hợp.

**Bài 5.** Có nên dùng `reduce(0, (a,b) -> a-b)` trên parallel stream để mô phỏng phép trừ tuần tự không?

**Đáp án:** Không, phép trừ không associative nên không đáp ứng yêu cầu giảm song song theo cách đó.

**Bài 6.** `isParallel() == true` có chứng minh từng callback chạy ở thread khác nhau không?

**Đáp án:** Không; nó cho biết chế độ của Stream, không chứng minh số thread/tốc độ hoặc lịch chạy cụ thể.

**Bài 7.** Muốn chuyển một Stream được tạo bằng `stream()` sang parallel, có cách nào khác việc gọi lại `parallelStream()`?

**Đáp án:** Có thể dùng `collection.stream().parallel()` trước terminal operation. Ngược lại, `collection.parallelStream().sequential()` đặt pipeline về chế độ tuần tự.

**Bài 8.** Stream có phải snapshot toàn bộ Collection khi gọi `stream()` không?

**Đáp án:** Không mặc định. Semantics khi nguồn thay đổi phụ thuộc vào nguồn/spliterator; nếu cần snapshot ổn định hãy tạo rõ ràng và tuân thủ hợp đồng nguồn.

## 14. Tài liệu tham khảo

- [Java SE 17 — Collection.stream() / parallelStream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [Java SE 17 — Stream API và nguyên tắc stateless/non-interfering](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — BaseStream.isParallel(), sequential(), parallel()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html).
- [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).

**Ghi nhớ:** `Collection.stream()` tạo Stream tuần tự, còn `Collection.parallelStream()` yêu cầu một Stream có thể xử lý song song nhưng không hứa mức song song hay tốc độ trong mọi implementation. Cả hai dùng cùng các thao tác Stream; khác biệt quan trọng nằm ở **cách thực thi, bảo toàn thứ tự, an toàn của callback và chi phí phối hợp**. Chọn tuần tự mặc định, giữ dữ liệu nguồn ổn định và chỉ bật parallel khi hợp đồng phép tính cùng phép đo hiệu năng cho phép.
