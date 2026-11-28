# Parallel stream, thứ tự xử lý và điều kiện sử dụng an toàn

**Parallel stream** là cách yêu cầu Java Stream API chia công việc trên một nguồn dữ liệu thành những phần có thể xử lý đồng thời. Trong Java 27, việc chuyển một luồng xử lý từ tuần tự sang song song thường chỉ cần gọi `parallelStream()` hoặc `parallel()`. Tuy nhiên, thay đổi cú pháp nhỏ này có thể ảnh hưởng đến **thứ tự thực thi**, **tính an toàn của trạng thái chia sẻ**, **cách tổng hợp kết quả** và **hiệu năng**.

Bài học thuộc chương **Xử lý dữ liệu bằng Stream**, trong phạm vi Java 27 và các kiến thức hiện vẫn được áp dụng. Trọng tâm không phải là “làm mọi stream chạy song song”, mà là biết **khi nào parallel stream cho kết quả đúng, khi nào có thể có lợi và khi nào nên giữ xử lý tuần tự**.

## 1. Từ stream tuần tự đến stream song song

Stream biểu diễn một pipeline gồm nguồn, các thao tác trung gian và một thao tác kết thúc (*terminal operation*).

~~~text
Nguồn dữ liệu
     |
     v
 filter -> map -> sorted    (intermediate operations)
                         |
                         v
                  collect / sum / count
                    (terminal operation)
~~~

Các thao tác trung gian như `filter` và `map` thường **lazy**: chỉ tạo mô tả xử lý, chưa tự duyệt dữ liệu. Pipeline bắt đầu thực thi khi gọi một terminal operation.

Ví dụ tuần tự:

~~~java
import java.util.List;

public class SequentialExample {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

        long total = numbers.stream()
                .filter(n -> n % 2 == 0)
                .mapToLong(n -> (long) n * n)
                .sum();

        System.out.println(total); // 4 + 16 + 36 = 56
    }
}
~~~

Phiên bản yêu cầu xử lý song song:

~~~java
long total = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .mapToLong(n -> (long) n * n)
        .sum();

System.out.println(total); // 56
~~~

Hai pipeline có **cùng ý nghĩa tính toán**. Với đầu vào này, phép cộng trên kiểu nguyên không bị tràn số, nên kết quả mong đợi là 56. Điều khác biệt là cách runtime có thể phân công xử lý các phần của nguồn.

### 1.1. Ba cách bật hoặc tắt chế độ song song

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4);

boolean a = numbers.stream().isParallel();          // false
boolean b = numbers.parallelStream().isParallel();  // true
boolean c = numbers.stream().parallel().isParallel(); // true

long sum = numbers.parallelStream()
        .sequential()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(sum); // 10
~~~

- `collection.stream()` thường tạo stream tuần tự.
- `collection.parallelStream()` thường tạo stream song song.
- `stream.parallel()` yêu cầu chuyển pipeline sang chế độ song song.
- `stream.sequential()` yêu cầu chế độ tuần tự.
- `isParallel()` cho biết chế độ của stream, **không chứng minh rằng công việc thực tế đã được chạy bởi nhiều thread**.

Trong cùng một pipeline, cách gọi `parallel()` và `sequential()` ảnh hưởng đến chế độ thực thi của toàn pipeline; đừng nghĩ mỗi đoạn của pipeline mặc nhiên có một chế độ riêng cố định.

### 1.2. Song song không đồng nghĩa nhanh hơn

Chuyển sang `parallelStream()` là **yêu cầu runtime thử khai thác song song**, không phải cam kết chương trình sẽ nhanh hơn hoặc tạo đúng một số lượng thread nhất định.

Cần trả chi phí phân chia nguồn, lập lịch các tác vụ, trao đổi dữ liệu và tổng hợp kết quả. Với dữ liệu ít hoặc phép xử lý quá nhẹ, các chi phí này có thể lớn hơn phần thời gian tiết kiệm.

## 2. Parallel stream xử lý dữ liệu như thế nào?

Một parallel stream thường cố gắng chia nguồn thành các phần nhỏ để xử lý độc lập rồi kết hợp kết quả.

~~~text
                Nguồn: [1, 2, 3, 4, 5, 6, 7, 8]
                               |
                    chia thành các phần
                     /                 \
           [1, 2, 3, 4]           [5, 6, 7, 8]
              /     \                /     \
            [1,2]  [3,4]         [5,6]   [7,8]
               \     /               \     /
              kết hợp               kết hợp
                     \               /
                      kết quả cuối cùng
~~~

Sơ đồ mang tính minh họa: runtime không bắt buộc chia đúng một nửa, dùng đúng bốn tác vụ hay chạy từng nhánh trên một thread riêng.

### 2.1. Vai trò của Spliterator

Nguồn dữ liệu thường cung cấp `Spliterator` để hỗ trợ duyệt và chia dữ liệu. `Spliterator.trySplit()` cố gắng tạo một spliterator con phụ trách một phần phần tử còn lại.

Một số nguồn thuận tiện để chia là mảng, `ArrayList` và các dải số có kích thước xác định. Các nguồn khó chia đều, không biết kích thước hoặc phải đi tuần tự từ đầu để xác định phần tử có thể tạo ra ít lợi ích hơn.

Các đặc tính như `SIZED`, `SUBSIZED` và `ORDERED` giúp Stream API hiểu nguồn tốt hơn. Tuy nhiên, chỉ nhìn vào đặc tính nguồn **không đủ** để kết luận parallel stream chắc chắn hiệu quả.

### 2.2. Runtime và luồng thực thi

Trong các triển khai JDK phổ biến, parallel stream thường sử dụng cơ sở hạ tầng fork/join, bao gồm khả năng thực thi qua common `ForkJoinPool`. Đây là chi tiết vận hành cần quan sát khi đo hiệu năng, không phải lý do để ứng dụng giả định thứ tự, số lượng thread hoặc thread cụ thể cho mỗi phần tử.

Một pipeline song song có thể chạy các callback trên nhiều worker thread. Vì vậy:

- Không giả định thread gọi terminal operation sẽ xử lý mọi phần tử.
- Không giả định mỗi phần tử được gán cho một thread ổn định.
- Không dựa vào số thread cụ thể để bảo đảm kết quả.
- Không xem parallel stream là API lựa chọn executor riêng cho từng pipeline.

Nếu cần điều khiển pool, chính sách lập lịch, hủy tác vụ hoặc giới hạn số yêu cầu đồng thời một cách chính xác, cần cân nhắc mô hình tác vụ thích hợp hơn thay vì mặc nhiên dùng parallel stream.

## 3. Ba khái niệm về thứ tự cần phân biệt

Một điểm dễ nhầm là **thứ tự phần tử của nguồn** không nhất thiết trùng với **thứ tự callback chạy**.

### 3.1. Encounter order: thứ tự gặp phần tử

*Encounter order* là thứ tự phần tử được xác định bởi nguồn hoặc một thao tác trong pipeline.

- `List.of("An", "Bình", "Chi")` có thứ tự gặp theo thứ tự danh sách.
- `ArrayList` có thứ tự gặp theo vị trí chỉ số.
- `TreeSet` có thứ tự duyệt theo comparator/natural ordering.
- `HashSet` không cam kết một thứ tự gặp ổn định.
- `sorted()` thiết lập thứ tự cho kết quả của thao tác sắp xếp.

Nếu nguồn có encounter order, nhiều thao tác Stream sẽ bảo toàn ngữ nghĩa thứ tự đó khi hợp đồng của thao tác yêu cầu, kể cả khi các phần tử được xử lý trên nhiều thread.

### 3.2. Thứ tự thực thi callback

Khi thực hiện:

~~~java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 8)
        .parallel()
        .forEach(System.out::println);
~~~

Không thể dự đoán thứ tự dòng in. Ví dụ, một lần chạy có thể thấy 6 trước 1, nhưng lần khác có thể thấy 1 trước 6.

Kết quả in phụ thuộc lịch chạy của tác vụ. **Không có một thứ tự in cố định** cho `forEach` trên parallel stream.

### 3.3. Thứ tự trong kết quả terminal operation

Một terminal operation như `toList()` có thể giữ encounter order:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 8)
        .parallel()
        .boxed()
        .toList();

System.out.println(values);
// [1, 2, 3, 4, 5, 6, 7, 8]
~~~

Tuy công việc có thể hoàn thành không theo thứ tự, `toList()` trả về danh sách theo encounter order nếu stream có encounter order.

**Kết luận:** Có encounter order không đồng nghĩa callback được gọi tuần tự, và callback chạy không theo thứ tự không đồng nghĩa kết quả cuối cùng phải mất thứ tự.

## 4. forEach và forEachOrdered

`forEach` thích hợp khi hành động trên từng phần tử không cần quan hệ thứ tự.

~~~java
List<String> names = List.of("An", "Bình", "Chi");

names.parallelStream()
        .forEach(System.out::println);
// Thứ tự các dòng không được bảo đảm.
~~~

Khi bắt buộc các hành động được quan sát theo encounter order, dùng `forEachOrdered`:

~~~java
names.parallelStream()
        .forEachOrdered(System.out::println);
// An
// Bình
// Chi
~~~

Với stream có encounter order, `forEachOrdered` thực hiện các hành động theo thứ tự đó. API còn quy định quan hệ *happens-before* giữa hành động của một phần tử và hành động của phần tử kế tiếp. Tuy nhiên, **không được giả định tất cả hành động chạy trên cùng một thread**.

### 4.1. Tại sao forEachOrdered có thể làm giảm lợi ích song song?

Để bảo đảm thứ tự, runtime có thể phải chờ kết quả của phần tử trước trước khi thực hiện hành động cho phần tử sau. Nếu công việc quan trọng nằm ngay trong `forEachOrdered`, việc phối hợp có thể trở thành nút thắt.

Nếu mục tiêu là tạo một danh sách đầu ra có thứ tự, thường nên chọn:

~~~java
List<String> upper = names.parallelStream()
        .map(String::toUpperCase)
        .toList();

System.out.println(upper); // [AN, BÌNH, CHI]
~~~

Thay vì tự tạo danh sách mutable và đẩy dữ liệu vào từ `forEachOrdered`. Cách dùng `toList()` nói rõ ý định kết quả và tránh tác dụng phụ không cần thiết.

### 4.2. forEachOrdered không biến toàn pipeline thành tuần tự

~~~java
names.parallelStream()
        .map(name -> name.toUpperCase())
        .forEachOrdered(System.out::println);
~~~

`map` vẫn có thể được tính song song và không theo thứ tự thực thi, trong khi hành động cuối của `forEachOrdered` được điều phối theo encounter order.

Vì vậy, không dùng `forEachOrdered` như một cách “sửa” các lỗi truy cập trạng thái chung nằm trong `map` hay `filter`.

## 5. findFirst, findAny và ý nghĩa của “phần tử đầu tiên”

Hai terminal operation thường gây nhầm lẫn:

- `findFirst()` ưu tiên phần tử đầu tiên theo encounter order nếu stream có thứ tự.
- `findAny()` có thể trả một phần tử phù hợp bất kỳ; cách này cho phép runtime linh hoạt hơn trong xử lý song song.

~~~java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("An", "Bình", "Chi", "Dung");

Optional<String> first = names.parallelStream()
        .filter(name -> name.length() >= 3)
        .findFirst();

System.out.println(first.orElse("Không có")); // Bình
~~~

Với cùng dữ liệu:

~~~java
Optional<String> any = names.parallelStream()
        .filter(name -> name.length() >= 3)
        .findAny();

System.out.println(any.orElse("Không có"));
// Có thể là Bình, Chi hoặc Dung.
~~~

Nếu nghiệp vụ cần “bản ghi đầu tiên theo thứ tự ưu tiên” thì `findAny` **không thể thay thế** `findFirst`.

Nếu chỉ cần tìm một phần tử bất kỳ đáp ứng điều kiện, `findAny` thể hiện đúng ý định và thường cho runtime thêm cơ hội tối ưu khi song song.

Lưu ý: khi nguồn không có encounter order, `findFirst` cũng không thể suy ra một “phần tử đầu tiên” ổn định theo nghĩa nghiệp vụ.

## 6. ordered, unordered và sorted

### 6.1. unordered() bỏ yêu cầu thứ tự, không tự xáo trộn dữ liệu

`unordered()` đánh dấu pipeline **không cần duy trì encounter order**. Nó không có nghĩa là xáo trộn phần tử ngẫu nhiên.

~~~java
List<Integer> selected = IntStream.rangeClosed(1, 100)
        .parallel()
        .unordered()
        .limit(5)
        .boxed()
        .toList();

System.out.println(selected);
~~~

Khi đã bỏ yêu cầu thứ tự, năm phần tử được chọn có thể không phải 1, 2, 3, 4, 5. Đừng gán ngữ nghĩa “năm số đầu” cho kết quả này.

Trong một số trường hợp, bỏ yêu cầu thứ tự giúp `limit`, `distinct` hoặc các thao tác liên quan hoạt động hiệu quả hơn khi xử lý song song. Chỉ dùng nếu **bài toán thực sự không cần thứ tự**.

### 6.2. sorted() thiết lập một thứ tự có nghĩa

~~~java
List<Integer> ordered = List.of(9, 2, 7, 1, 5)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(ordered); // [1, 2, 5, 7, 9]
~~~

`sorted()` là một thao tác **stateful**: thường phải quan sát và sắp xếp nhiều phần tử trước khi phát kết quả. Dù có thể được thực hiện song song, nó không phải thao tác cục bộ độc lập trên từng phần tử như `map`.

Nếu sử dụng `sorted().findFirst()` để lấy giá trị nhỏ nhất, hãy cân nhắc `min(...)`: phép toán `min` nêu trực tiếp mục đích và có thể tránh chi phí sắp xếp toàn bộ dữ liệu.

### 6.3. Các thao tác cần đặc biệt chú ý đến thứ tự

| Thao tác | Ý nghĩa khi nguồn có thứ tự | Điều cần cân nhắc khi song song |
|---|---|---|
| `map`, `filter` | Bảo toàn encounter order về mặt ngữ nghĩa | Callback có thể chạy không theo thứ tự |
| `distinct` | Giữ phần tử đầu tiên trong các phần tử trùng, nếu có thứ tự | Có thể cần phối hợp và trạng thái |
| `sorted` | Tạo thứ tự đã sắp xếp | Thường cần buffer/phối hợp |
| `limit(n)` | Chọn n phần tử đầu theo encounter order | Đôi khi đắt hơn với pipeline song song |
| `skip(n)` | Bỏ n phần tử đầu theo encounter order | Có thể đòi hỏi phối hợp |
| `takeWhile` | Lấy tiền tố liên tiếp thỏa điều kiện trên stream có thứ tự | Bảo đảm tiền tố có thể tốn chi phí |
| `dropWhile` | Bỏ tiền tố liên tiếp thỏa điều kiện trên stream có thứ tự | Không đồng nghĩa `filter` |
| `findFirst` | Chọn phần tử phù hợp đầu tiên theo encounter order | Có thể cần chờ các phần trước |
| `findAny` | Chọn phần tử phù hợp bất kỳ | Thường linh hoạt hơn khi song song |

Với `takeWhile` hoặc `dropWhile` trên một nguồn không có thứ tự, ý nghĩa về “tiền tố” thay đổi theo đặc tả của các thao tác; đừng sử dụng chúng thay `filter` nếu yêu cầu là xử lý mọi phần tử đáp ứng điều kiện.

## 7. Điều kiện quan trọng nhất: không can thiệp vào nguồn

Stream API yêu cầu các hàm xử lý thông thường **non-interfering**: không thay đổi cấu trúc hoặc dữ liệu của nguồn đang được pipeline tiêu thụ theo cách trái hợp đồng.

Ví dụ sai với `ArrayList`:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4, 5));

// Ví dụ KHÔNG AN TOÀN: tuyệt đối không dùng trong nghiệp vụ.
numbers.parallelStream()
        .filter(n -> {
            if (n % 2 == 0) {
                numbers.remove(n);
            }
            return true;
        })
        .count();
~~~

Đoạn mã thay đổi chính collection nguồn trong callback. Hậu quả có thể là ngoại lệ, phần tử bị bỏ qua, kết quả không đúng hoặc hành vi không xác định. Việc không xuất hiện `ConcurrentModificationException` trong một lần chạy **không chứng minh mã đã an toàn**.

Cách đúng để loại phần tử chẵn khỏi một collection mutable là thực hiện riêng:

~~~java
numbers.removeIf(n -> n % 2 == 0);
~~~

Nếu chỉ cần tạo danh sách các phần tử lẻ mà không thay đổi nguồn:

~~~java
List<Integer> odd = numbers.stream()
        .filter(n -> n % 2 != 0)
        .toList();
~~~

Khi pipeline đang hoạt động, hãy coi dữ liệu nguồn là **không bị sửa** trong thời gian terminal operation tiêu thụ nó, trừ khi nguồn và cách thao tác có hợp đồng concurrent rõ ràng và thuật toán tương thích.

## 8. Stateless behavior: tránh trạng thái chia sẻ trong callback

Ngoài non-interference, các callback như `map` và `filter` nên **stateless**: kết quả mỗi lần gọi chỉ phụ thuộc vào đầu vào và dữ liệu bất biến có liên quan, không dựa vào trạng thái được thay đổi bởi các lời gọi khác.

### 8.1. Ví dụ sai: ghi vào ArrayList từ nhiều worker

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> results = new ArrayList<>();

// Ví dụ SAI: nhiều thread có thể gọi ArrayList.add đồng thời.
IntStream.range(0, 10_000)
        .parallel()
        .forEach(results::add);
~~~

`ArrayList` không được thiết kế để nhiều thread đồng thời sửa mà không có đồng bộ thích hợp. Kết quả có thể mất phần tử, sai kích thước hoặc xảy ra lỗi.

Cách đúng là để Stream API thu thập kết quả:

~~~java
List<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(results.size()); // 10000
~~~

`toList()` tạo danh sách kết quả không cho sửa đổi; với nguồn có encounter order như `IntStream.range`, thứ tự kết quả vẫn là thứ tự của dải số.

### 8.2. Vì sao synchronizedList chưa chắc là giải pháp tốt nhất?

Có thể bọc `ArrayList` bằng `Collections.synchronizedList(...)` để bảo vệ mỗi lần thêm. Tuy nhiên, dùng `parallelStream().forEach(synchronizedList::add)`:

- Vẫn có thể không giữ encounter order.
- Tạo điểm tranh chấp khóa khi nhiều worker cùng ghi.
- Biểu diễn bài toán kém rõ ràng hơn `collect` hoặc `toList`.

Một container thread-safe không tự động biến thuật toán dựa trên thứ tự, chỉ số hay điều kiện nhiều bước thành đúng.

### 8.3. AtomicInteger không tự sửa lỗi logic

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

List<Integer> observed = List.of(10, 20, 30, 40)
        .parallelStream()
        .map(value -> value + counter.getAndIncrement())
        .toList();
~~~

`AtomicInteger` giúp các thao tác tăng đếm có tính nguyên tử, nhưng **không bảo đảm phần tử nào nhận giá trị đếm nào**. Kết quả có thể thay đổi tùy thứ tự callback chạy.

Nếu nghiệp vụ cần gắn chỉ số với phần tử theo vị trí, hãy làm việc với dải chỉ số rõ ràng hoặc giữ xử lý tuần tự:

~~~java
List<String> names = List.of("An", "Bình", "Chi");

List<String> indexed = IntStream.range(0, names.size())
        .mapToObj(i -> i + ": " + names.get(i))
        .toList();

System.out.println(indexed);
// [0: An, 1: Bình, 2: Chi]
~~~

Việc dùng chỉ số từ nguồn không đổi tạo ánh xạ xác định mà không phải chia sẻ bộ đếm tăng dần giữa các worker.

## 9. Giảm dữ liệu (reduction): kết hợp đúng cách

Parallel stream cần kết hợp kết quả của nhiều nhánh. Vì vậy, phép gộp dùng trong `reduce` phải phù hợp với việc tách và kết hợp theo các nhóm khác nhau.

### 9.1. Tính kết hợp (associativity)

Một phép toán nhị phân được gọi là kết hợp khi:

\[
(a \circ b) \circ c = a \circ (b \circ c)
\]

Ví dụ, cộng số nguyên theo mô hình số học phù hợp là phép kết hợp. Phép trừ không kết hợp:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Nếu đưa phép trừ vào `reduce` và mong kết quả giống cách tính tuần tự, kết quả song song có thể khác:

~~~java
// KHÔNG DÙNG như một reduction bảo đảm kết quả số học:
// Phép trừ không kết hợp.
int result = List.of(10, 3, 2)
        .parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

`reduce` không có nhiệm vụ bảo toàn trật tự nhóm phép toán mà ứng dụng mong đợi khi phép gộp vi phạm hợp đồng kết hợp.

### 9.2. Identity phải là phần tử trung hòa

Với `reduce(identity, accumulator)`, identity phải không làm thay đổi kết quả khi kết hợp:

~~~java
int sum = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 10
~~~

`0` là identity của phép cộng. Một lỗi thường gặp là dùng giá trị khởi tạo khác identity:

~~~java
// SAI về mặt logic reduction:
int sum = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(10, Integer::sum);
~~~

Mỗi nhánh có thể được bắt đầu với identity, nên cách gộp song song có thể cộng giá trị 10 nhiều lần. Nếu cần cộng thêm phí cố định một lần, hãy tính tổng bằng identity 0 rồi cộng phí sau:

~~~java
int fee = 10;

int total = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum)
        + fee;

System.out.println(total); // 20
~~~

### 9.3. Hàm kết hợp phải không gây tác dụng phụ

~~~java
long total = List.of(10, 20, 30, 40)
        .parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 100
~~~

Đoạn mã dùng phép tổng hợp có hợp đồng phù hợp với song song. Tránh để accumulator hoặc combiner ghi vào một biến hay collection dùng chung không được thiết kế cho truy cập đồng thời.

### 9.4. reduce ba tham số

Overload `reduce(identity, accumulator, combiner)` đặc biệt quan trọng khi loại kết quả khác loại phần tử nguồn:

~~~java
import java.util.List;

long totalLength = List.of("Java", "Stream", "API")
        .parallelStream()
        .reduce(
                0L,
                (subtotal, word) -> subtotal + word.length(),
                Long::sum
        );

System.out.println(totalLength); // 13
~~~

Trong ví dụ này:

- Identity: `0L`.
- Accumulator: cộng độ dài một từ vào tổng tạm.
- Combiner: kết hợp tổng tạm của các nhánh bằng phép cộng.

`combiner` phải tương thích với `accumulator`; cả hai cùng với identity cần đáp ứng hợp đồng của `reduce`. Không dùng một đối tượng mutable duy nhất làm identity rồi thay đổi nó trong các nhánh, vì có thể dẫn tới trạng thái chia sẻ sai.

Với bài toán tính tổng chiều dài, cách rõ ràng hơn là:

~~~java
long totalLength = List.of("Java", "Stream", "API")
        .parallelStream()
        .mapToLong(String::length)
        .sum();
~~~

## 10. Dấu phẩy động và tính xác định của kết quả

Cần phân biệt **kết quả xác định về mặt toán học** với **kết quả tính toán thực tế của kiểu dấu phẩy động**.

Với `double` hoặc `float`, phép cộng không bảo đảm tính kết hợp theo số học thực do làm tròn:

~~~text
(a + b) + c có thể khác a + (b + c)
~~~

Vì parallel stream có thể gom nhóm phép cộng khác với stream tuần tự, các phép tính tổng số thực có thể có sai khác ở các chữ số cuối.

~~~java
double sum = List.of(1e16, 1.0, -1e16)
        .parallelStream()
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

Không nên dùng phép so sánh bằng tuyệt đối giữa kết quả `double` song song và một chuỗi cộng thủ công theo thứ tự cố định để chứng minh thuật toán sai hoặc đúng. Với yêu cầu tính tiền chính xác, dùng mô hình tiền tệ như số đơn vị nhỏ nhất dạng nguyên (cents, đồng, v.v.) hoặc `BigDecimal` cùng chính sách làm tròn phù hợp.

**Lưu ý:** Ngay cả khi phép gộp kết hợp, nếu kết quả có thể tràn kiểu nguyên, cần xem xét giới hạn miền giá trị và dùng kiểu phù hợp. Song song không tự giải quyết vấn đề tràn số.

## 11. collect và cách thu thập kết quả an toàn

`collect` và các collector được thiết kế đúng giúp kết hợp các kết quả cục bộ mà không bắt người dùng tự đồng bộ một danh sách hay map dùng chung.

### 11.1. toList giữ thứ tự của nguồn có thứ tự

~~~java
List<String> names = List.of("An", "Bình", "Chi");

List<String> upper = names.parallelStream()
        .map(String::toUpperCase)
        .toList();

System.out.println(upper);
// [AN, BÌNH, CHI]
~~~

Kết quả của `Stream.toList()` không cho phép sửa đổi. Nếu cần một `ArrayList` mutable:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<String> upper = names.parallelStream()
        .map(String::toUpperCase)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Không nhầm `Stream.toList()` với `Collectors.toList()`: API của `Collectors.toList()` không bảo đảm một kiểu cụ thể hay tính mutable của danh sách trả về.

### 11.2. groupingBy: nhóm phần tử theo khóa

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String category, String name) {}

List<Product> products = List.of(
        new Product("Book", "Java"),
        new Product("Tool", "IDE"),
        new Product("Book", "Algorithms")
);

Map<String, List<Product>> byCategory = products.parallelStream()
        .collect(Collectors.groupingBy(Product::category));

System.out.println(byCategory.get("Book"));
// [Product[category=Book, name=Java],
//  Product[category=Book, name=Algorithms]]
~~~

`groupingBy` dùng cơ chế collector phù hợp để gộp kết quả của các nhánh. Không nên thay nó bằng việc tự gọi `map.computeIfAbsent(...)` trên `HashMap` dùng chung trong một `forEach` song song.

Thứ tự duyệt các khóa của map kết quả không được bảo đảm chỉ vì stream đầu vào có thứ tự. Nếu muốn map có thứ tự rõ ràng, cần chọn map/comparator phù hợp.

### 11.3. groupingByConcurrent và trade-off thứ tự

~~~java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> counts =
        products.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Product::category,
                        Collectors.counting()
                ));

System.out.println(counts.get("Book")); // 2
~~~

`groupingByConcurrent` trả collector có tính **concurrent** và **unordered**. Nó có thể phù hợp với trường hợp cần tổng hợp theo khóa mà **không quan tâm encounter order**.

Tuy nhiên:

- Kết quả là một `ConcurrentMap`, không có thứ tự khóa được cam kết.
- Không được giả định thứ tự phần tử của các danh sách nằm trong map giống thứ tự nguồn nếu downstream collector tạo danh sách.
- Concurrent collector không có nghĩa mọi đối tượng phần tử hay mọi downstream container đều phù hợp để bị ứng dụng sửa đồng thời sau khi collect.
- Không phải cứ thêm chữ `Concurrent` là sẽ nhanh hơn; hãy đo hiệu năng với dữ liệu thực tế.

### 11.4. toConcurrentMap và khóa trùng

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

record Sale(String region, long amount) {}

List<Sale> sales = List.of(
        new Sale("VN", 100),
        new Sale("US", 200),
        new Sale("VN", 300)
);

ConcurrentMap<String, Long> totals =
        sales.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        Sale::region,
                        Sale::amount,
                        Long::sum
                ));

System.out.println(totals.get("VN")); // 400
~~~

Ở đây có hai phần tử cùng khóa `VN`, nên cần hàm gộp `Long::sum`. Nếu sử dụng overload `toMap` hoặc `toConcurrentMap` không có merge function và phát sinh khóa trùng, collector có thể ném `IllegalStateException`.

Không nên suy luận thứ tự đưa từng phần tử vào map từ thứ tự ban đầu của stream.

## 12. Khi nào dùng parallelStream hợp lý?

Parallel stream có khả năng hữu ích nếu hội đủ nhiều điều kiện:

1. **Đầu vào đủ lớn** để chi phí phân chia/phối hợp không áp đảo công việc hữu ích.
2. **Công việc trên mỗi phần tử tương đối đáng kể** và có thể xử lý độc lập.
3. **Nguồn dễ chia**, chẳng hạn mảng, `ArrayList` hoặc `IntStream.range`.
4. **Các callback stateless, non-interfering**, không sửa nguồn và không dùng trạng thái chia sẻ có tác động đến kết quả.
5. **Phép tổng hợp hợp lệ**, bao gồm associativity và identity/combiner đúng.
6. **Không có yêu cầu thứ tự thực thi không cần thiết**, hoặc ứng dụng chấp nhận chi phí duy trì thứ tự.
7. **Máy thực thi có đủ tài nguyên**, và mức độ song song không tranh chấp tài nguyên quan trọng với tác vụ khác.
8. **Đã đo hiệu năng** trên dữ liệu, JDK và hạ tầng phù hợp.

### 12.1. Ví dụ có thể phù hợp

Tính toán độc lập trên một lượng lớn dữ liệu trong bộ nhớ:

~~~java
import java.util.stream.IntStream;

long count = IntStream.range(0, 1_000_000)
        .parallel()
        .filter(n -> {
            long x = (long) n * n + 7;
            return x % 13 == 0;
        })
        .count();

System.out.println(count);
~~~

Đây chỉ là ví dụ về cấu trúc pipeline an toàn, **không phải khẳng định rằng bản song song của công việc rất nhẹ này sẽ nhanh hơn**. Lợi ích phải được đo trong tình huống thật.

### 12.2. Những trường hợp thường không phù hợp

- Dữ liệu chỉ có vài chục phần tử và phép xử lý rất đơn giản.
- Mỗi phần tử được xử lý bằng một API không thread-safe, không có cơ chế bảo vệ phù hợp.
- Callback sửa collection nguồn hoặc ghi vào biến mutable chia sẻ.
- Bài toán đòi các tác dụng phụ xảy ra đúng thứ tự và phải chờ phần tử trước.
- Stream có nhiều thao tác stateful và yêu cầu duy trì encounter order chặt chẽ.
- Công việc chủ yếu là chờ mạng, truy vấn database hoặc I/O chặn.
- Ứng dụng cần giới hạn số lời gọi đồng thời tới dịch vụ bên ngoài hay cần timeout/cancellation theo từng tác vụ.

Parallel stream thường thích hợp nhất với **tính toán trên bộ nhớ, thiên về CPU và độc lập theo phần tử**. Đối với nhiều tác vụ I/O độc lập, Java hiện đại có các lựa chọn rõ ràng hơn, như executor hoặc virtual threads, tùy kiến trúc và yêu cầu điều phối.

## 13. I/O, common pool và nguy cơ làm nghẽn tài nguyên

Một câu hỏi thường gặp là:

> Có nên dùng `parallelStream()` để gọi API HTTP hoặc thực hiện truy vấn database trên từng phần tử?

Với các thao tác chặn lâu, cần thận trọng. Parallel stream không cung cấp trực tiếp giao diện cấp phát một executor độc lập cho mỗi pipeline hoặc cách quản lý giới hạn truy cập API bên ngoài theo nhu cầu nghiệp vụ.

Nếu nhiều tác vụ bị chặn khi giữ worker, hiệu suất của ứng dụng có thể bị ảnh hưởng. Với JDK phổ biến, việc chia sẻ cơ sở hạ tầng fork/join giữa các công việc cũng tạo nguy cơ tranh chấp tài nguyên.

Ví dụ không nên mặc nhiên dùng trong hệ thống gọi dịch vụ ngoài:

~~~java
// Minh họa một lựa chọn có thể KHÔNG phù hợp:
// List<Response> responses = ids.parallelStream()
//         .map(id -> httpClient.callBlocking(id))
//         .toList();
~~~

Vấn đề không phải parallel stream luôn sai với I/O, mà là nó **không tự giải quyết giới hạn kết nối, retry, timeout, rate limiting, cancellation hoặc quản lý áp lực tải**.

Nếu thiết kế cần xử lý nhiều I/O chặn độc lập, cân nhắc cơ chế tác vụ có executor/giới hạn concurrency riêng. Ví dụ Java hỗ trợ virtual threads qua `Executors.newVirtualThreadPerTaskExecutor()` cho một số trường hợp I/O chặn phù hợp. **Virtual threads không làm CPU-bound code tự chạy nhanh hơn**, và cũng không thay thế giới hạn tải cho dịch vụ ngoài.

## 14. Không được suy luận hiệu năng chỉ từ số lượng CPU

Một cách đánh giá parallel stream là so sánh thời gian tuần tự và song song. Nhưng đo một lần bằng `System.currentTimeMillis()` không đủ để ra quyết định đáng tin cậy.

### 14.1. Các yếu tố làm sai lệch phép đo

- JVM warm-up và JIT compilation.
- Garbage collection và việc cấp phát bộ nhớ.
- Kích thước và phân phối dữ liệu.
- Số lõi CPU thực có sẵn trong môi trường triển khai.
- Tranh chấp CPU từ tác vụ khác.
- Chi phí chia nguồn và gộp kết quả.
- Đặc tính của collector, đặc biệt khi có thứ tự.
- Tốc độ truy cập bộ nhớ và mức độ cache locality.

Đối với microbenchmark, có thể dùng công cụ chuyên dụng như **JMH** và thiết kế benchmark tránh việc runtime tối ưu bỏ kết quả không được sử dụng.

### 14.2. Đo đúng mục tiêu

Hãy so sánh hai pipeline tạo **cùng một kết quả nghiệp vụ**:

~~~java
long sequential = values.stream()
        .mapToLong(Long::longValue)
        .sum();

long parallel = values.parallelStream()
        .mapToLong(Long::longValue)
        .sum();

if (sequential != parallel) {
    throw new AssertionError("Kết quả khác nhau");
}
~~~

Điều kiện `sequential == parallel` trong ví dụ số nguyên đơn giản là một bước kiểm tra hợp lý khi phép tổng hợp có cùng ngữ nghĩa. Tuy nhiên, chỉ kiểm tra bằng nhau không đủ để chứng minh thread safety hay tính đúng đắn của các phép xử lý phức tạp.

Nếu lợi ích không rõ ràng, phiên bản tuần tự thường dễ đọc, dễ theo dõi, dễ kiểm thử và dễ dự đoán chi phí hơn.

## 15. Thiết kế kết quả xác định thay vì phụ thuộc lịch thread

Khi nghiệp vụ yêu cầu đầu ra nhất quán, cần biết những phần nào phải xác định:

| Yêu cầu | Thiết kế phù hợp |
|---|---|
| Danh sách đầu ra phải theo thứ tự danh sách nguồn | Nguồn có encounter order; dùng `map/filter` và `toList()` |
| Chỉ cần tổng độc lập thứ tự | Dùng phép reduce kết hợp, identity đúng hoặc primitive `sum()` |
| Cần lấy phần tử đầu tiên theo ưu tiên | Sắp xếp/định nghĩa encounter order, rồi `findFirst()` |
| Chỉ cần một phần tử thỏa điều kiện | Có thể dùng `findAny()` |
| Không quan tâm thứ tự của tập kết quả | Dùng collector phù hợp; cân nhắc `unordered()` |
| Cần các hành động theo thứ tự gặp | `forEachOrdered()`, đồng thời hiểu chi phí |
| Cần thứ tự và side effects phức tạp | Cân nhắc stream tuần tự hoặc thuật toán khác |
| Cần bất biến trạng thái toàn hệ thống | Đồng bộ hoặc transaction theo nghiệp vụ; stream tự nó không đủ |

Tránh phụ thuộc vào log, thứ tự của `Thread.currentThread().getName()` hay thứ tự các lời gọi callback để xác nhận kết quả nghiệp vụ.

## 16. Ví dụ hoàn chỉnh: tổng hợp doanh thu và đơn hàng ưu tiên

Ví dụ sử dụng `record` để biểu diễn đơn hàng bất biến ở mức các trường, các phép gộp hợp lệ và một nguồn `List` có encounter order.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ParallelSalesDemo {
    record Sale(
            String id,
            String category,
            long amountInDong
    ) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S-001", "BOOK", 120_000),
                new Sale("S-002", "TECH", 550_000),
                new Sale("S-003", "BOOK", 80_000),
                new Sale("S-004", "TECH", 350_000),
                new Sale("S-005", "FOOD", 60_000)
        );

        // 1. Tổng giá trị đơn hàng: phép gộp độc lập.
        long total = sales.parallelStream()
                .mapToLong(Sale::amountInDong)
                .sum();

        // 2. Chọn đơn hàng theo điều kiện.
        // toList giữ encounter order của nguồn List.
        List<String> highValueIds = sales.parallelStream()
                .filter(s -> s.amountInDong() >= 100_000)
                .map(Sale::id)
                .toList();

        // 3. Tổng hợp theo nhóm với collector thông thường.
        Map<String, Long> byCategory = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        Collectors.summingLong(Sale::amountInDong)
                ));

        // 4. Collector concurrent khi không cần thứ tự nhóm.
        ConcurrentMap<String, Long> concurrentTotals =
                sales.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                Sale::category,
                                Collectors.summingLong(Sale::amountInDong)
                        ));

        System.out.println("Total = " + total);
        System.out.println("High-value IDs = " + highValueIds);
        System.out.println("BOOK = " + byCategory.get("BOOK"));
        System.out.println(
                "TECH = " + concurrentTotals.get("TECH")
        );
    }
}
~~~

Kết quả mong đợi:

~~~text
Total = 1160000
High-value IDs = [S-001, S-002, S-004]
BOOK = 200000
TECH = 900000
~~~

Giải thích:

1. `Sale` là record với các trường `String` và `long`; không có đối tượng mutable bên trong, nên việc đọc các giá trị này từ nhiều worker là phù hợp.
2. `mapToLong(...).sum()` biểu diễn tổng hợp tốt hơn việc tự quản lý một biến đếm dùng chung.
3. `highValueIds` giữ thứ tự encounter order của danh sách gốc.
4. `groupingBy` thu thập và gộp theo khóa mà không yêu cầu callback ghi vào `HashMap` chung.
5. `groupingByConcurrent` phù hợp khi không cần thứ tự của nhóm và muốn dùng collector concurrent. Không được giả định nó luôn nhanh hơn `groupingBy`.
6. Không in trực tiếp các map để kiểm tra một thứ tự khóa cố định; ví dụ lấy giá trị theo khóa cụ thể.

Nếu số lượng đơn hàng nhỏ, bản `stream()` tuần tự có thể đơn giản và nhanh hơn. Kết quả đúng không phải bằng chứng rằng cấu hình song song là tối ưu.

## 17. Các lỗi thường gặp và cách sửa

| Vấn đề | Vì sao nguy hiểm | Cách làm phù hợp |
|---|---|---|
| Dùng `parallel().forEach(list::add)` với `ArrayList` | Nhiều worker sửa cùng nguồn kết quả không thread-safe | Dùng `toList()` hoặc collector phù hợp |
| Dùng `AtomicInteger` để gắn thứ tự cho phần tử | Thứ tự callback không cố định | Dùng chỉ số nguồn hoặc xử lý tuần tự |
| Sửa collection nguồn trong `filter` | Vi phạm non-interference | Tách thao tác sửa, hoặc dùng `removeIf` trước/sau |
| Dùng `findAny` khi cần phần tử đầu | Không bảo đảm encounter-first | Dùng `findFirst` với nguồn có thứ tự |
| Dùng `forEach` để in bản báo cáo theo thứ tự | Hành động có thể xảy ra không theo thứ tự | `forEachOrdered` hoặc collect thành dữ liệu có thứ tự |
| Gọi `unordered()` rồi vẫn kỳ vọng `limit(5)` lấy năm phần tử đầu | Đã bỏ yêu cầu encounter order | Không dùng `unordered()` nếu thứ tự có ý nghĩa |
| Dùng phép trừ trong `reduce` | Không kết hợp | Chọn phép tổng hợp kết hợp đúng |
| Dùng identity không trung hòa | Có thể bị tính lại khi tách nhánh | Chọn identity/combiner đúng hợp đồng |
| Đưa `StringBuilder` chung vào `reduce` | Trạng thái mutable và chia sẻ sai | Dùng `Collectors.joining()` |
| Dùng `groupingByConcurrent` rồi kỳ vọng danh sách trong nhóm giữ thứ tự | Collector concurrent là unordered | Dùng collector có chính sách thứ tự phù hợp |
| Cho rằng `forEachOrdered` làm tất cả callback tuần tự | Chỉ cam kết thứ tự hành động terminal | Đảm bảo các callback trước đó stateless |
| Cho rằng nhiều lõi CPU đồng nghĩa nhanh hơn | Chi phí quản lý có thể vượt lợi ích | Benchmark trên workload thực |
| Dùng parallel stream cho I/O chặn không giới hạn | Khó kiểm soát pool, rate limit, timeout | Thiết kế tác vụ/executor và giới hạn concurrency riêng |

## 18. Checklist trước khi chọn parallel stream

1. **Tính đúng đắn:** Các callback có stateless và non-interfering không?
2. **Nguồn:** Collection có bị sửa bởi thread khác trong thời gian duyệt không?
3. **Kết quả:** Có thực sự cần encounter order không?
4. **Terminal operation:** `forEach`, `findAny`, `toList`, `reduce` có phù hợp với yêu cầu không?
5. **Phép gộp:** Identity và combiner có đúng, phép toán có kết hợp không?
6. **Kiểu số:** Có thể tràn số nguyên hay bị ảnh hưởng bởi sai khác làm tròn dấu phẩy động không?
7. **Dữ liệu:** Kích thước nguồn đủ lớn và phân chia hiệu quả không?
8. **Bản chất công việc:** CPU-bound hay chờ I/O, database và network?
9. **Tài nguyên:** Có nguy cơ chiếm dụng worker hoặc gây tranh chấp với xử lý khác không?
10. **Đo lường:** Đã so sánh với pipeline tuần tự bằng cùng dữ liệu và điều kiện chưa?
11. **Kiểm thử:** Đã kiểm tra nhiều kích thước, đầu vào rỗng, nguồn có/không thứ tự, kết quả thu thập và việc nhiều lần thực thi chưa?
12. **Khả năng bảo trì:** Lợi ích song song có đủ rõ để đánh đổi độ phức tạp và khó khăn khi debug không?

## 19. Tóm tắt

- Parallel stream cho runtime cơ hội chia xử lý, nhưng **không bảo đảm nhanh hơn**.
- *Encounter order*, thứ tự callback chạy và thứ tự kết quả là ba khái niệm khác nhau.
- `forEach` không bảo đảm thứ tự hành động trên stream song song; `forEachOrdered` giữ encounter order cho terminal action khi nguồn có thứ tự.
- `toList()` giữ thứ tự phần tử của nguồn có encounter order và trả danh sách không cho sửa đổi.
- `findFirst()` và `findAny()` phục vụ hai yêu cầu khác nhau.
- `unordered()` bỏ ràng buộc thứ tự, không phải thao tác shuffle.
- Hàm xử lý phải tránh sửa nguồn và không phụ thuộc trạng thái chia sẻ có thể thay đổi.
- Dùng collector và các phép tổng hợp kết hợp, identity đúng thay vì tự ghi vào một collection dùng chung.
- `groupingByConcurrent` có thể phù hợp với tổng hợp không cần thứ tự, nhưng không tự động nhanh hoặc đúng hơn cho mọi bài toán.
- Đặc biệt thận trọng với thao tác stateful, I/O chặn và các phép số thực.
- Giữ `stream()` tuần tự là lựa chọn hợp lý khi không có bằng chứng rằng song song mang lại lợi ích.

## Tài liệu tham khảo chính thức

- [Stream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [IntStream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html)
- [Collectors — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html)
- [Collector — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collector.html)
- [BaseStream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/BaseStream.html)
- [Spliterator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterator.html)
- [Collection — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html)
- [ForkJoinPool — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Executors — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html)
