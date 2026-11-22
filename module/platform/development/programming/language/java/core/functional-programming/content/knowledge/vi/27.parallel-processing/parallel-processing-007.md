# `forEachOrdered()` và chi phí duy trì thứ tự trong Java Stream

Trong Java Stream, `parallel()` cho phép việc xử lý các phần tử được chia thành nhiều tác vụ. Nhưng chương trình đôi khi vẫn cần **thực hiện hành động theo đúng thứ tự gặp phần tử** (*encounter order*): xuất báo cáo theo thứ tự nhập, ghi dòng ra console, hoặc áp dụng một chuỗi thao tác có phụ thuộc vào thứ tự.

`forEachOrdered()` là terminal operation dành cho yêu cầu đó. Nó bảo đảm **hành động cuối** được thực hiện theo encounter order **khi stream có encounter order**. Đổi lại, framework có thể phải điều phối, chờ hoặc lưu đệm kết quả; phần chi phí này đôi khi làm lợi ích của xử lý song song giảm đáng kể.

Điểm quan trọng: **`forEachOrdered()` không có nghĩa toàn bộ pipeline đã chạy tuần tự**. Các phép `map()`, `filter()` và các công việc upstream vẫn có thể chạy song song; thứ tự được ràng buộc ở các hành động của `forEachOrdered()`.

## 1. Encounter order và execution order là hai khái niệm khác nhau

**Encounter order** là thứ tự logic của các phần tử được định nghĩa bởi nguồn hoặc các phép toán trong pipeline. Ví dụ `List.of("A", "B", "C")` có thứ tự gặp `A → B → C`.

**Execution order** là lịch thực tế mà các callback chạy trên các luồng xử lý. Một parallel stream có thể thực hiện `map("C")` trước `map("A")`, nhưng kết quả được ghép thành `A, B, C` nếu terminal operation phải giữ thứ tự.

```text
Nguồn List có thứ tự:       A ------ B ------ C ------ D
Lịch map có thể diễn ra:    C, A, D, B  (không có bảo đảm)
Kết quả .toList():         [A, B, C, D]
Hành động forEachOrdered:   A, B, C, D
```

Dòng “lịch map” chỉ minh họa **một khả năng**, không phải lịch cố định của JVM. Một ordered parallel stream vẫn có encounter order, còn việc các callback được thực thi ở luồng nào hoặc vào thời điểm nào là vấn đề khác.

Một số nguồn và operation liên quan:

| Nguồn hoặc operation | Bảo đảm encounter order |
| --- | --- |
| `List.stream()`, `List.parallelStream()` | Có; theo thứ tự phần tử của list |
| `Arrays.stream(array)` | Có; theo thứ tự chỉ số |
| `LinkedHashSet.stream()` | Có; theo thứ tự iteration được định nghĩa |
| `HashSet.stream()` | Không có encounter order được bảo đảm |
| `stream.sorted()` | Tạo một thứ tự sắp xếp cho kết quả đi tiếp |
| `stream.unordered()` | Bỏ yêu cầu giữ encounter order nếu có |

`parallel()` không tự động làm mất encounter order. Ngược lại, `unordered()` không tự động bật parallelism và cũng **không có nghĩa xáo trộn ngẫu nhiên**.

## 2. `forEach()` và `forEachOrdered()`: hợp đồng khác nhau

Cả hai đều là **terminal operation**, trả `void` và nhận một `Consumer<? super T>` để thực hiện hành động cho các phần tử còn lại trong stream.

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

Đây là chữ ký API rút gọn từ `Stream<T>`, không phải chương trình Java độc lập.

| Tiêu chí | `forEach()` | `forEachOrdered()` |
| --- | --- | --- |
| Có cần stream ordered để có thứ tự xác định? | Bản thân phương thức **không bảo đảm** thứ tự khi chạy parallel | Có; tuân thủ encounter order nếu được định nghĩa |
| Trên ordered parallel stream | Action có thể chạy không theo encounter order | Action phải diễn ra theo encounter order |
| Luồng thực thi action | Có thể là nhiều luồng | Có thể do các luồng khác nhau thực hiện; không cam kết một luồng cố định |
| Quan hệ giữa hai action liên tiếp | Không có bảo đảm thứ tự/happens-before theo encounter order từ phương thức | Action của phần tử trước **happens-before** action của phần tử sau |
| Chi phí tiềm năng | Ít ràng buộc phối hợp về thứ tự hơn | Có thể phải chờ/đồng bộ/lưu đệm để bảo toàn thứ tự |
| Mục đích | Thực hiện action khi thứ tự không quan trọng | Thực hiện action khi thứ tự đầu ra là yêu cầu |

Với ordered stream tuần tự, `forEach()` thường được quan sát theo thứ tự duyệt. Tuy nhiên, khi thiết kế mã có thể chuyển sang song song, không nên coi đó là cam kết của `parallelStream().forEach()`. Nếu cần **hợp đồng thứ tự rõ ràng**, hãy dùng `forEachOrdered()` hoặc thiết kế đầu ra bằng `toList()`/`collect()`.

### Ví dụ không có kết quả cố định

```java
List<Integer> nums = List.of(1, 2, 3, 4);
nums.parallelStream().forEach(System.out::println);
```

Đây là snippet trong phương thức và cần `import java.util.List;`. Bốn số đều có thể được in ra nếu không có exception, nhưng **thứ tự in không xác định**. Một lần có thể nhìn thấy `3, 2, 4, 1`; lần khác có thể lại là `1, 2, 3, 4`. Không được viết kiểm thử trông đợi một lịch in cụ thể.

Dùng:

```java
nums.parallelStream().forEachOrdered(System.out::println);
```

với chính `List` này sẽ in `1`, `2`, `3`, `4` theo thứ tự gặp, mỗi số một dòng.

## 3. Java 17+ chạy được: kết quả có thứ tự dù map song song

Lưu toàn bộ chương trình sau thành `ForEachOrderedDemo.java`:

```java
import java.util.List;

public class ForEachOrderedDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 1, 3, 2);

        System.out.println("source = " + numbers);

        List<Integer> mapped = numbers.parallelStream()
                .map(n -> n * 10)
                .toList();
        System.out.println("mapped = " + mapped);

        System.out.println("ordered actions:");
        numbers.parallelStream()
                .map(n -> n * 10)
                .forEachOrdered(n -> System.out.println("value = " + n));

        System.out.println("sorted actions:");
        numbers.parallelStream()
                .sorted()
                .forEachOrdered(n -> System.out.println("value = " + n));

        int first = numbers.parallelStream()
                .findFirst()
                .orElseThrow();
        System.out.println("first = " + first);

        List<Integer> firstTwo = numbers.parallelStream()
                .limit(2)
                .toList();
        System.out.println("firstTwo = " + firstTwo);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ForEachOrderedDemo.java
java ForEachOrderedDemo
```

**Stdout xác định:**

```text
source = [4, 1, 3, 2]
mapped = [40, 10, 30, 20]
ordered actions:
value = 40
value = 10
value = 30
value = 20
sorted actions:
value = 1
value = 2
value = 3
value = 4
first = 4
firstTwo = [4, 1]
```

**Giải thích kỹ:**

1. `numbers` là một `List` có encounter order `4, 1, 3, 2`.
2. `map(n -> n * 10)` có thể chạy trên nhiều luồng theo lịch bất kỳ, nhưng `toList()` của ordered stream giữ thứ tự logic và trả `[40, 10, 30, 20]`.
3. `forEachOrdered()` buộc bốn **hành động in** theo thứ tự các giá trị được gặp sau `map`. Nó **không** buộc các lời gọi `map` chạy theo đúng thứ tự thời gian `4, 1, 3, 2`.
4. `sorted()` thay encounter order bằng thứ tự `1, 2, 3, 4`. `forEachOrdered()` tôn trọng thứ tự mới đó.
5. `findFirst()` trả phần tử đầu theo encounter order, là `4`; `limit(2)` giữ hai phần tử đầu là `[4, 1]`. Chúng cũng giữ ngữ nghĩa ordered mặc dù có thể được thực thi song song.

Chương trình tạo **một stream mới** cho mỗi phép terminal. Sau `toList()`, `forEachOrdered()` hoặc `findFirst()`, đối tượng stream đó không được sử dụng lại.

## 4. Bảo đảm happens-before áp dụng cho phần nào?

Tài liệu của `forEachOrdered()` nêu rõ: việc thực hiện action của **một phần tử** *happens-before* việc thực hiện action của **phần tử kế tiếp** theo encounter order.

Ví dụ:

```java
List<Integer> values = List.of(1, 2, 3);
values.parallelStream()
        .forEachOrdered(n -> System.out.println("item " + n));
```

Hành động `println("item 1")` phải đứng trước hành động `println("item 2")`, và hành động của `2` đứng trước `3`. Nhưng Java **không cam kết action nào cũng chạy trên cùng một thread**; framework có thể lựa chọn thread khác cho các phần tử.

Đừng mở rộng bảo đảm này sang những điều không được hứa:

- Không có bảo đảm rằng `map()`, `filter()` hoặc `peek()` **upstream** đều chạy theo encounter order.
- Không có bảo đảm về việc có chính xác bao nhiêu thread tham gia xử lý nguồn.
- Không có bảo đảm `parallelStream()` sẽ nhanh hơn chỉ vì công việc ở phía trước có thể song song.
- Nếu action **chỉ gửi một công việc bất đồng bộ** sang executor rồi trả về, `forEachOrdered()` có thể đảm bảo thứ tự **gửi/lập lịch**, nhưng **không tự đảm bảo** các công việc bất đồng bộ hoàn tất theo thứ tự đó.

Ví dụ về khác biệt cuối cùng: nếu `action` gọi `executor.submit(task)`, các task có thể chạy đồng thời sau khi được submit. Muốn kết quả của task hoàn tất theo thứ tự, cần một cơ chế bổ sung như chuỗi phụ thuộc, hàng đợi tuần tự hoặc thu kết quả trước rồi công bố theo thứ tự.

### Có phải `forEachOrdered()` làm cho mọi side effect đều an toàn?

Không. Nó ràng buộc thứ tự giữa những **action của chính terminal operation ấy**. Nếu `map` trước đó cập nhật một `ArrayList` dùng chung, hoặc các chương trình khác cùng sửa dữ liệu đó, vẫn có thể xảy ra race condition.

Ví dụ sai thiết kế:

```java
List<Integer> shared = new ArrayList<>();
List<Integer> source = List.of(1, 2, 3, 4);

source.parallelStream()
        .map(n -> {
            shared.add(n); // SAI: cập nhật ArrayList dùng chung ở upstream.
            return n * 2;
        })
        .forEachOrdered(System.out::println);
```

Đây là snippet **để chỉ ra lỗi**, cần `java.util.List` và `java.util.ArrayList`, không dùng cho ứng dụng thực. Bảo đảm của `forEachOrdered` không biến lời gọi `shared.add(n)` trong `map` thành thao tác đồng bộ/an toàn.

## 5. Chi phí duy trì encounter order đến từ đâu?

Khi action không cần thứ tự, các phần của nguồn có thể được xử lý và tiêu thụ độc lập hơn. Khi action phải theo thứ tự, framework cần đảm bảo phần tử ở vị trí sau **không được thực hiện action trước phần tử đứng trước**, dù phần tử đứng sau đã tính xong.

Các nguồn chi phí có thể có:

1. **Chờ phần tử trước:** một tác vụ tính xong phần tử `C` nhưng phải đợi `A`, `B` hoàn thành để xuất đúng thứ tự.
2. **Phối hợp giữa các nhánh:** framework phải theo dõi cách ghép các đoạn có encounter order, không thể tùy tiện phát kết quả ngay khi một nhánh sẵn sàng.
3. **Lưu đệm tạm:** một số kết quả có thể cần được giữ lại cho đến khi phần trước hoàn tất; điều này tạo thêm nhu cầu bộ nhớ.
4. **Giới hạn mức song song ở đầu ra:** nếu action rất chậm (ví dụ ghi ra một kênh xuất duy nhất), việc bắt action theo thứ tự có thể trở thành nút thắt và triệt tiêu lợi ích của tính toán upstream.
5. **Overhead quản lý parallelism:** với pipeline nhỏ, chi phí chia việc, phối hợp và gộp có thể lớn hơn thời gian của từng phép `map` hoặc `filter`.

**Không có con số giảm tốc cố định.** Chi phí phụ thuộc nguồn/spliterator, số lượng phần tử, cách chia công việc, mức độ nặng của `map`, khả năng dừng sớm, hệ điều hành, JVM và loại tác dụng phụ cuối cùng. Không được kết luận `forEachOrdered` luôn chậm hơn `forEach` trong mọi phép đo, cũng không được kết luận nó biến toàn bộ pipeline thành sequential.

### Ví dụ ngữ nghĩa “chờ phần trước”

```text
Encounter order:     A -> B -> C -> D
Tính upstream xong:  C, D, B, A
forEachOrdered:      A, B, C, D

C và D dù đã sẵn sàng cũng không được chạy action
trước A và B.
```

Sơ đồ là ví dụ khái niệm, không mô tả một thuật toán cụ thể mà JDK bắt buộc phải dùng.

## 6. So sánh ba chiến lược khi cần đầu ra có thứ tự

### Cách 1 — tuần tự từ đầu đến cuối

```java
source.stream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
```

Cách này đơn giản khi công việc nhẹ, dữ liệu ít hoặc action cuối chiếm phần lớn thời gian. Các snippet có `source`, `transform`, `writeResult` do ứng dụng định nghĩa; không phải chương trình Java độc lập.

### Cách 2 — tính toán song song, xuất theo thứ tự bằng `forEachOrdered()`

```java
source.parallelStream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
```

Phần `transform` có thể chạy song song; `writeResult` được gọi theo encounter order. Đây là cách phù hợp nếu **bắt buộc gọi action theo đúng thứ tự**, chẳng hạn gửi các thông điệp tới một đích không cho phép đảo thứ tự.

Hãy chắc rằng `transform` là **stateless, non-interfering** và không ghi vào trạng thái chia sẻ không an toàn. Với hành động có I/O, cần chính sách xử lý lỗi, thử lại và trạng thái đã ghi một phần.

### Cách 3 — thu kết quả theo thứ tự rồi xử lý I/O riêng

```java
List<Result> results = source.parallelStream()
        .map(this::transform)
        .toList();

results.forEach(this::writeResult);
```

Snippet cần `java.util.List` và các kiểu/hàm `Result`, `transform`, `writeResult` của ứng dụng. `toList()` giữ encounter order khi upstream ordered; `forEach` trên list duyệt theo thứ tự của list. Cách này tách rõ **biến đổi** khỏi **tác dụng phụ**, giúp kiểm thử và xử lý thất bại tại ranh giới dễ hơn.

Tuy nhiên nó phải lưu **toàn bộ danh sách kết quả** trước khi ghi, nên có thể tiêu thụ nhiều bộ nhớ; nó không phải lựa chọn tối ưu cho mọi nguồn lớn. Trong khi đó, `forEachOrdered()` cũng có thể cần buffer nội bộ nhưng không nhất thiết lưu tất cả kết quả dưới dạng list lâu dài do ứng dụng giữ.

Chọn cách nào phụ thuộc yêu cầu: **cần gọi action theo thứ tự**, **cần toàn bộ kết quả để validate trước khi ghi**, hay **chỉ muốn xử lý một luồng dữ liệu tuần tự đơn giản**.

## 7. Khi nào nên bỏ yêu cầu thứ tự?

Nếu thứ tự của action **không có ý nghĩa**, chẳng hạn các phép cập nhật độc lập được thiết kế idempotent và thread-safe, `forEach()` có thể tránh ràng buộc thứ tự không cần thiết.

```java
source.parallelStream()
        .forEach(this::processIndependent);
```

Đây là snippet trong class có `source` và `processIndependent` do ứng dụng định nghĩa. Trước khi dùng phải bảo đảm mỗi action độc lập, dữ liệu được bảo vệ trước ghi đồng thời, không yêu cầu sắp hàng trước/sau, và xử lý lỗi có chính sách rõ ràng.

Không nên dùng `parallelStream().forEach(sharedArrayList::add)` để tạo list kết quả, vì `ArrayList` không thread-safe; dù thay bằng list đồng bộ hóa thì thứ tự thêm vẫn phụ thuộc lịch callback. Nếu mục tiêu là tạo list, dùng `toList()` hoặc `collect(Collectors.toList())` thay vì tác dụng phụ bên ngoài.

### `unordered()` không phải công cụ để “vừa nhanh vừa giữ thứ tự”

```java
List<Integer> values = List.of(10, 20, 30, 40);
values.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

Trên pipeline này, `unordered()` đã bỏ ràng buộc encounter order. Vì vậy `forEachOrdered()` **không còn cơ sở để bắt buộc in `10,20,30,40`** như nguồn ban đầu. Lệnh gọi vẫn hợp lệ, nhưng không có thứ tự cụ thể nào được bảo đảm.

Nếu cần thứ tự tăng dần một cách xác định, có thể áp đặt order bằng `sorted()` trên những dữ liệu so sánh được rồi dùng `forEachOrdered()`. Nhưng sorting cũng có chi phí, nên không thêm `sorted()` chỉ để khôi phục một kỳ vọng thứ tự vô cớ.

## 8. Đừng nhầm với `findFirst()`, `findAny()`, `limit()` và `toList()`

Đây là những API khác nhau về ngữ nghĩa, dù cùng liên quan đến encounter order:

| API | Bảo đảm quan trọng |
| --- | --- |
| `forEach()` | Thực hiện action, không đảm bảo encounter order trên parallel stream |
| `forEachOrdered()` | Thực hiện action theo encounter order của stream nếu có |
| `toList()` | Trả list có phần tử theo encounter order nếu có, không hứa thứ tự chạy callback upstream |
| `findFirst()` | Tìm phần tử đầu theo encounter order, nếu có |
| `findAny()` | Cho phép chọn phần tử bất kỳ |
| `limit(n)` | Với ordered stream, chỉ chọn tối đa n phần tử đầu theo encounter order |
| `sorted()` | Áp đặt thứ tự sắp xếp trước những bước sau |
| `unordered()` | Cho phép từ bỏ yêu cầu encounter order |

Một `parallelStream().limit(3).forEachOrdered(action)` trên list ordered chỉ thực hiện action cho tối đa ba phần tử đầu. `limit` được đặt **trước** terminal `forEachOrdered`, nên lựa chọn phần tử và thứ tự gọi action là hai bước ngữ nghĩa khác nhau.

Đặc biệt, `findFirst()` và `limit()` trên ordered parallel stream cũng có thể phát sinh chi phí duy trì thứ tự. Không nên bật `unordered()` chỉ để tăng tốc nếu kết quả cần “đầu tiên” theo dữ liệu đầu vào.

## 9. Trường hợp action thất bại hoặc tác vụ có tác dụng phụ

Ví dụ một action ghi file và ném exception sau khi ghi được vài dòng. `forEachOrdered()` không cung cấp transaction hay rollback:

```java
results.parallelStream().forEachOrdered(this::writeResult);
```

Đây là snippet minh họa; `results`, `writeResult` thuộc ứng dụng. Khi một action thất bại, những action đã thực hiện trước đó có thể đã tạo tác dụng phụ. Không nên nhầm “đúng thứ tự” với “nguyên tử” hoặc “chạy chính xác một lần” trong hệ thống phân tán.

Nếu cần cập nhật tất cả hoặc không cập nhật gì, hãy dùng transaction ở nguồn dữ liệu, tệp tạm/đổi tên nguyên tử khi phù hợp, hoặc một cơ chế điều phối rõ ràng. Nếu hành động có thể được gửi lại sau lỗi mạng, cần xử lý idempotency hoặc cơ chế nhận diện thao tác lặp.

Khi có xử lý bất đồng bộ, cần phân biệt:

- **Thứ tự gọi callback:** điều mà `forEachOrdered()` bảo đảm cho ordered stream.
- **Thứ tự gửi công việc ra executor:** có thể theo thứ tự khi lệnh submit nằm trực tiếp trong callback.
- **Thứ tự hoàn thành công việc bất đồng bộ:** không được `forEachOrdered()` tự động bảo đảm.
- **Thứ tự commit ở database/HTTP:** do hệ thống đích và giao thức quyết định.

Bảo đảm thứ tự chỉ có ý nghĩa khi xác định đúng **hành động nào** cần được xếp thứ tự.

## 10. Đo hiệu năng đúng cách

Để đánh giá chi phí, nên so sánh **cùng công việc** và **cùng yêu cầu kết quả**, tránh đo sai do in console hoặc gọi mạng có độ trễ biến động.

Các kịch bản đáng đo:

1. `source.stream().map(f).forEachOrdered(noopOrConsumer)`: đường xử lý tuần tự.
2. `source.parallelStream().map(f).forEachOrdered(noopOrConsumer)`: tính toán song song, action ordered.
3. `source.parallelStream().map(f).toList()`: biến đổi song song và thu kết quả có thứ tự, không có action ngoài.
4. Chỉ nếu **nghiệp vụ không cần order**, so sánh thêm `parallelStream().forEach(action)`. Không coi nó tương đương về hợp đồng với `forEachOrdered` nếu thứ tự thực sự có ý nghĩa.

Nên dùng **JMH** để benchmark: warm-up JVM, nhiều lần đo, tránh dead-code elimination, kiểm soát số luồng/kích thước nguồn. Đo bằng một lần `System.nanoTime()` quanh `println` thường không phản ánh hiệu năng xử lý Stream vì bị chi phối bởi I/O, JIT, scheduler và đồng bộ hóa.

Cẩn thận khi thiết kế consumer/no-op của benchmark: nếu terminal action không tạo hiệu ứng quan sát được, phải đảm bảo framework/harness không khiến phép đo vô nghĩa; hãy tiêu thụ dữ liệu theo cách được JMH hỗ trợ. Với workload có I/O, nên đo riêng CPU transform và chi phí biên I/O rồi mới đo tổng.

**Không có ngưỡng kích thước chung** để nói “trên N phần tử thì parallel + forEachOrdered nhanh hơn”. Kết quả tùy chi phí `f`, bộ nhớ, nguồn, phần việc ở downstream và số lõi thực tế.

## 11. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `parallelStream()` tự làm mất encounter order | Parallelism là chế độ thực thi, không tự bỏ thứ tự logic | Phân biệt ordered/unordered với sequential/parallel |
| Dùng `forEach()` song song để in theo thứ tự nguồn | `forEach` không đảm bảo thứ tự action | Dùng `forEachOrdered` trên ordered stream |
| Nghĩ `forEachOrdered` buộc `map` chạy tuần tự | Bảo đảm thứ tự chỉ ràng buộc action terminal | Giữ upstream stateless/non-interfering |
| Cho rằng mọi action chạy trên một thread | JDK không cam kết thread cố định | Không dùng thread identity làm hợp đồng |
| Dùng `forEachOrdered` để tạo list qua biến mutable ngoài | Tác dụng phụ không cần thiết, dễ khó kiểm thử | Dùng `toList`/`collect` để tạo kết quả |
| Gọi `unordered().forEachOrdered` rồi đòi đúng thứ tự gốc | Đã bỏ encounter order | Không gọi `unordered` khi cần thứ tự |
| Dùng `forEachOrdered` trong action submit task rồi tin task kết thúc có thứ tự | Chỉ thứ tự callback/submit được ràng buộc | Điều phối completion riêng |
| Nghĩ ordered action là transaction | I/O có thể thất bại giữa chừng, để lại phần đã ghi | Dùng cơ chế transaction/rollback/idempotency phù hợp |
| Tuyên bố `forEachOrdered` luôn chậm hơn hoặc luôn nhanh hơn | Không có cam kết hiệu năng phổ quát | Benchmark đúng workload và yêu cầu order |
| Tái sử dụng Stream sau terminal `forEachOrdered` | Stream đã bị tiêu thụ | Tạo stream mới từ nguồn cho lần xử lý tiếp theo |

## 12. Tự kiểm tra kiến thức

**Câu 1.** Với `List.of(3,1,2).parallelStream().forEachOrdered(System.out::println)`, ba dòng xuất hiện theo thứ tự nào?

**Đáp án:** `3`, `1`, `2`, vì list có encounter order và `forEachOrdered` tuân thủ thứ tự đó.

**Câu 2.** Có thể kết luận `map(n -> heavy(n))` chạy theo thứ tự `3,1,2` không?

**Đáp án:** Không. Nó có thể được thực thi trên các luồng và thời điểm khác nhau; chỉ các action terminal được xếp theo encounter order.

**Câu 3.** `forEachOrdered()` bảo đảm tất cả action chạy trên cùng một thread không?

**Đáp án:** Không. Java có thể sử dụng các thread khác nhau; bảo đảm nằm ở thứ tự và quan hệ happens-before giữa các action.

**Câu 4.** Nếu callback của `forEachOrdered` submit task bất đồng bộ rồi trả về, các task có chắc kết thúc theo thứ tự submit không?

**Đáp án:** Không. Scheduler có thể hoàn tất chúng theo lịch khác; cần cơ chế điều phối riêng.

**Câu 5.** Vì sao `parallelStream().forEachOrdered()` có thể không nhanh bằng `parallelStream().forEach()`?

**Đáp án:** Framework có thể cần chờ phần tử đứng trước, phối hợp các nhánh, giữ kết quả tạm và tuần tự hóa các action quan sát được để duy trì order.

**Câu 6.** Nếu chỉ muốn tạo danh sách biến đổi theo thứ tự list nguồn, có nhất thiết dùng `forEachOrdered(list::add)` không?

**Đáp án:** Không. `map(...).toList()` thường ngắn, rõ và tránh phải tích lũy vào trạng thái bên ngoài.

## Ghi nhớ

- `forEachOrdered()` là **terminal operation** thực hiện action theo **encounter order nếu stream có thứ tự**.
- Với ordered parallel stream, các action được thực hiện theo thứ tự và action trước **happens-before** action tiếp theo; **không** bảo đảm thread cố định hoặc upstream xử lý tuần tự.
- Chi phí có thể đến từ **chờ, phối hợp, buffering và bottleneck ở đầu ra**; không có hệ số giảm tốc cố định.
- Nếu chỉ cần kết quả có thứ tự, `toList()`/`collect()` thường rõ hơn việc dùng biến tích lũy ngoài rồi `forEachOrdered`.
- Nếu thứ tự không quan trọng, `forEach()` có thể giảm ràng buộc, nhưng action phải an toàn khi chạy đồng thời.
- `unordered()` bỏ nghĩa vụ giữ thứ tự; không dùng nếu kết quả cần theo thứ tự nguồn.
- Thứ tự gọi action khác với **thứ tự hoàn tất async work**, **thứ tự commit I/O** và **tính nguyên tử** của thao tác.
