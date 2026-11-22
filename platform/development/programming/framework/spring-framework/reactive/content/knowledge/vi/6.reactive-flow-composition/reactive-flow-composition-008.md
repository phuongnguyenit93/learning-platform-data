# `buffer`, `window` và `groupBy` trong Project Reactor

## 1. Bài toán: chia một luồng thành các phần nhỏ

Khi xử lý `Flux<T>` trong Spring WebFlux/Project Reactor, chúng ta thường cần gom một số phần tử để ghi theo lô, chia luồng thành các cửa sổ để xử lý liên tục, hoặc phân luồng theo một khóa nghiệp vụ. Reactor cung cấp ba họ operator quan trọng:

- **`buffer`:** gom nhiều phần tử nguồn thành một collection, thường là `List<T>`.
- **`window`:** chia luồng nguồn thành những **luồng con** `Flux<T>` dựa trên kích thước, thời gian hoặc điều kiện ranh giới.
- **`groupBy`:** phân luồng nguồn thành các `GroupedFlux<K,T>` theo khóa `K`, kể cả khi các phần tử cùng khóa nằm xen kẽ trong dữ liệu đầu vào.

Ba operator cùng phục vụ mục tiêu “chia luồng”, nhưng **khác kiểu kết quả, lúc phát nhóm, cách xử lý dữ liệu và chi phí tài nguyên**. Nhầm chúng dễ dẫn đến chờ mãi không có output, mất phần tử do `skip`, bộ nhớ tăng hoặc `groupBy` bị nghẽn bởi backpressure.

**Mục tiêu học tập:** chọn đúng operator từ yêu cầu nghiệp vụ; đọc được các kiểu `Flux<List<T>>`, `Flux<Flux<T>>`, `Flux<GroupedFlux<K,T>>`; giải thích nhóm không trùng/chồng lấp/bỏ khoảng; xây dựng pipeline tiêu thụ nhóm an toàn; kiểm thử bằng Java 17+ và StepVerifier.

## 2. So sánh ở một trang

| Tiêu chí | `buffer` | `window` | `groupBy` |
| --- | --- | --- | --- |
| Kết quả thường gặp | `Flux<List<T>>` | `Flux<Flux<T>>` | `Flux<GroupedFlux<K,T>>` |
| Tiêu chí chia | Số lượng, thời gian, predicate, publisher ranh giới | Số lượng, thời gian, predicate, publisher ranh giới | Khóa do hàm `keyMapper` tính |
| Nhóm phát ra là gì? | Collection đã được gom | Publisher con để tiêu thụ theo luồng | Publisher con kèm `key()` |
| Có cần `subscribe` luồng con? | Không; downstream nhận list | Có; phải tiêu thụ inner Flux | Có; phải tiêu thụ từng `GroupedFlux` |
| Có giữ dữ liệu trong collection? | Có, trong mỗi buffer | Không mặc định tạo `List`; có thể queue phần tử tùy operator/nhu cầu | Có thể queue phần tử theo nhóm nếu downstream chậm |
| Có thể chồng lấp? | Có ở các overload `buffer(size, skip)` và biến thể | Có ở `window(size, skip)` và biến thể | Không; mỗi phần tử đi vào đúng một nhóm khóa |
| Có thể có nhóm rỗng? | Ví dụ `bufferWhile` không phát buffer rỗng | Một số biến thể predicate như `windowWhile` có thể tạo window rỗng | Không; nhóm sinh ra do có phần tử mang khóa |
| Phù hợp nhất | Gửi lô hữu hạn, xuất danh sách, tích lũy ngắn hạn | Giữ cấu trúc stream theo các đoạn thời gian/kích thước | Xử lý theo tenant, loại sự kiện, mã khách hàng có số khóa kiểm soát |

Ví dụ nguồn `1,2,3,4,5,6,7`:

~~~text
Nguồn            1  2  3  4  5  6  7

buffer(3)         [1,2,3]  [4,5,6]  [7]
window(3)        (Flux 1,2,3) (Flux 4,5,6) (Flux 7)

groupBy(parity)   odd:  1,3,5,7
                  even: 2,4,6
~~~

Dù biểu diễn các window và buffer giống nhau trong ví dụ ngắn, **window là một publisher con** có thể được xử lý trong lúc dữ liệu đang đến, còn buffer là một collection đã hoàn thành theo ranh giới của nó.

## 3. `buffer(n)`: gom theo số lượng

`Flux<T>.buffer(int maxSize)` phát ra một `Flux<List<T>>`. Mỗi lần có đủ `maxSize` phần tử, operator đóng buffer hiện tại và gửi một list. Nếu nguồn hữu hạn kết thúc với phần dư, phần dư được phát thành list cuối ngắn hơn.

~~~java
Flux.range(1, 8)
    .buffer(3)
    .subscribe(batch -> System.out.println(batch));
~~~

Stdout của snippet trên (trong chương trình đã import `reactor.core.publisher.Flux`):

~~~text
[1, 2, 3]
[4, 5, 6]
[7, 8]
~~~

Điểm cần nhớ:

1. `buffer(3)` **không bảo đảm có list sau mỗi ba giây**; tiêu chí của overload này là **số phần tử**, không phải thời gian.
2. Nếu nguồn ngừng gửi nhưng **chưa hoàn tất** và buffer hiện chỉ có hai phần tử, `buffer(3)` có thể tiếp tục chờ phần tử thứ ba. Muốn phát khi hết thời gian chờ, cân nhắc `bufferTimeout`.
3. `List<T>` chiếm bộ nhớ chứa các phần tử được gom. Lô lớn hoặc nhiều buffer chồng lấp tăng chi phí bộ nhớ.
4. `buffer` không tự thực hiện database batch/transaction; nó chỉ gom phần tử. Bước tiếp theo như `concatMap(batch -> repository.saveBatch(batch))` mới quyết định cách lưu.
5. Kích thước list cuối có thể nhỏ hơn `maxSize`; không giả định mọi batch có kích thước bằng nhau.

Với `Flux.empty().buffer(3)`, không có list dữ liệu nào từ source. Khi cần một danh sách rỗng đại diện “không có kết quả” trong response, đó là một quyết định ở tầng nghiệp vụ, không nên mặc định mỗi operator buffer phát một list rỗng.

## 4. `window(n)`: chia thành những publisher con

`Flux<T>.window(int maxSize)` trả về `Flux<Flux<T>>`. Mỗi phần tử của luồng ngoài là **một `Flux<T>` con**, không phải `List<T>`.

~~~java
Flux.range(1, 8)
    .window(3)
    .concatMap(inner -> inner.collectList())
    .subscribe(windowAsList -> System.out.println(windowAsList));
~~~

Trong snippet này, ta **chủ động** gọi `collectList()` để minh họa phần tử của từng window bằng list. Stdout:

~~~text
[1, 2, 3]
[4, 5, 6]
[7, 8]
~~~

Nếu bỏ `collectList()`, downstream cần một cách khác để **subscribe/tiêu thụ từng inner Flux**. Chỉ ghi:

~~~java
Flux<Flux<Integer>> windows = Flux.range(1, 8).window(3);
~~~

mới là **tạo pipeline**; bản thân câu lệnh không in dữ liệu và không tự thực hiện xử lý từng phần tử bên trong.

Sự khác biệt quan trọng:

- `buffer` xuất mỗi `List<T>` khi buffer khép lại; nhiều phần tử đã được tập hợp thành một object.
- `window` có thể công bố một luồng con từ lúc nó mở. Downstream có thể xử lý phần tử bên trong nó **ngay khi chúng đến**, tùy toán tử ghép/nhu cầu.
- `window` không miễn phí: nếu mở inner window mà không tiêu thụ, queue/backpressure có thể khiến pipeline không tiến hoặc tăng bộ nhớ.
- Dùng `concatMap` khi muốn xử lý các window theo thứ tự và nối output tuần tự; dùng `flatMap` khi chấp nhận interleaving và muốn xử lý đồng thời (phải giới hạn concurrency khi cần).
- `window` **không đồng nghĩa** với tạo thread, scheduler hay xử lý song song. Muốn chuyển thread cần những operator và scheduler phù hợp.

Một ví dụ xử lý stream từng đoạn, không cần thu toàn bộ thành list:

~~~java
Flux<String> summaries = Flux.range(1, 9)
    .window(3)
    .concatMap(inner ->
        inner.reduce(0, Integer::sum)
             .map(sum -> "window-sum=" + sum)
    );
~~~

Snippet này phát:

~~~text
window-sum=6
window-sum=15
window-sum=24
~~~

`reduce` ở đây chỉ lưu trạng thái tổng, không giữ list toàn bộ phần tử. Tuy vậy, vì cần kết thúc mỗi window để ra tổng, nó vẫn phát kết quả theo ranh giới window.

## 5. `groupBy(keyMapper)`: chia theo khóa, không theo vị trí

`groupBy` tạo một `Flux<GroupedFlux<K,T>>`. Khi gặp phần tử có khóa `K` mới, operator mở một group ứng với khóa ấy. Những phần tử sau có cùng khóa có thể quay lại cùng group dù xen giữa là hàng chục phần tử mang khóa khác.

~~~java
Flux.just("A:1", "B:1", "A:2", "B:2", "A:3")
    .groupBy(value -> value.substring(0, 1))
    .flatMap(group ->
        group.collectList()
             .map(items -> group.key() + " -> " + items)
    )
    .sort()
    .subscribe(System.out::println);
~~~

Stdout (có `sort()` để trật tự kết quả ổn định):

~~~text
A -> [A:1, A:2, A:3]
B -> [B:1, B:2]
~~~

Ở đây:

- `group.key()` trả khóa của `GroupedFlux`.
- Phần tử `A:2` không tạo nhóm A thứ hai; nó đi vào nhóm A đã có.
- Một phần tử thuộc **chính xác một nhóm**, khác buffer/window chồng lấp.
- Group không rỗng vì nó được mở khi thực sự có phần tử mang khóa.
- `flatMap` dùng để **tiêu thụ tất cả group** đồng thời; `collectList()` trong ví dụ chỉ hợp lý do nguồn hữu hạn, nhỏ.

**`groupBy` khác `windowUntilChanged` / `bufferUntilChanged`:** nếu dữ liệu là `A,A,B,A`, `groupBy` phân tất cả A về **một group A**; operator chia theo **các đoạn giá trị liên tiếp** lại có thể tạo ba đoạn `[A,A]`, `[B]`, `[A]`. Chọn theo ý nghĩa nghiệp vụ: “mọi sự kiện của một khách hàng” khác “mỗi đợt liên tục mang cùng trạng thái”.

## 6. Chương trình Java 17+ đầy đủ, chạy và so sánh cả ba

Tạo dự án Gradle đơn giản. Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
}

application {
    mainClass = 'BatchingDemo'
}
~~~

Tạo `src/main/java/BatchingDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public final class BatchingDemo {
    public static void main(String[] args) {
        Flux<Integer> numbers = Flux.range(1, 9);

        List<List<Integer>> buffers = numbers
            .buffer(4)
            .collectList()
            .block();

        List<List<Integer>> windows = numbers
            .window(4)
            .concatMap(inner -> inner.collectList())
            .collectList()
            .block();

        List<List<Integer>> overlapping = numbers
            .buffer(4, 2)
            .collectList()
            .block();

        List<List<Integer>> gapped = numbers
            .buffer(2, 4)
            .collectList()
            .block();

        List<String> groups = numbers
            .groupBy(i -> i % 2 == 0 ? "even" : "odd")
            .flatMap(group ->
                group.collectList()
                     .map(items -> group.key() + "=" + items)
            )
            .sort()
            .collectList()
            .block();

        System.out.println("buffer(4): " + buffers);
        System.out.println("window(4): " + windows);
        System.out.println("buffer(4,2): " + overlapping);
        System.out.println("buffer(2,4): " + gapped);
        System.out.println("groupBy(parity): " + groups);
    }
}
~~~

Chạy bằng `gradle run --quiet` (hoặc `./gradlew run --quiet` nếu dự án có Gradle Wrapper). Stdout chính xác với nguồn `Flux.range(1,9)`:

~~~text
buffer(4): [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
window(4): [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
buffer(4,2): [[1, 2, 3, 4], [3, 4, 5, 6], [5, 6, 7, 8], [7, 8, 9], [9]]
buffer(2,4): [[1, 2], [5, 6], [9]]
groupBy(parity): [even=[2, 4, 6, 8], odd=[1, 3, 5, 7, 9]]
~~~

**Giải thích tính đúng của output:**

1. `buffer(4)` và `window(4)` đều chia 9 phần tử thành hai đoạn đủ bốn và một đoạn dư một. `window(4)` đã được chuyển sang list bằng `collectList()` chỉ để so sánh.
2. `buffer(4,2)` mở buffer mới sau mỗi hai phần tử, trong khi mỗi buffer có thể chứa bốn; vì vậy các buffer **chồng lấp**. Phần tử 3,4 xuất hiện trong hai buffer khác nhau. Cuối nguồn có những buffer chưa đủ bốn phần tử.
3. `buffer(2,4)` mở buffer ở phần tử thứ 1,5,9; mỗi buffer tối đa hai phần tử. Các phần tử 3,4,7,8 **không được đưa vào buffer nào**.
4. `groupBy` tạo hai nhóm theo chẵn/lẻ; mỗi giá trị ở đúng một nhóm. `sort()` cố định trật tự hiển thị vì các group có thể hoàn thành/emit theo thời điểm khác nhau.
5. `numbers` được xây từ `Flux.range` là nguồn lạnh có thể subscribe nhiều lần; mỗi phép `block()` trong ví dụ console chạy một pipeline riêng từ 1 tới 9. `block()` được dùng **chỉ trong main demo**, không đưa `block()` vào xử lý request reactive của Spring WebFlux.

## 7. Tham số `size` và `skip`: không trùng, chồng lấp, bỏ khoảng

Với `buffer(size, skip)` và `window(size, skip)`:

- `size` là kích thước tối đa của từng nhóm/cửa sổ.
- `skip` là số phần tử nguồn giữa **hai vị trí mở nhóm liên tiếp**, không phải “bỏ qua luôn bấy nhiêu phần tử”.
- `size == skip`: các nhóm liền nhau, không chồng lấp và không tạo khoảng trống.
- `size > skip`: **chồng lấp**; cùng phần tử có thể thuộc nhiều buffer/window.
- `size < skip`: **có khoảng trống**; phần tử thuộc khoảng trống bị loại khỏi output của operator này.

Ví dụ từ nguồn 1…10:

| Biểu thức | Những nhóm phát ra |
| --- | --- |
| `buffer(5)` | [1,2,3,4,5], [6,7,8,9,10] |
| `buffer(5,3)` | [1,2,3,4,5], [4,5,6,7,8], [7,8,9,10], [10] |
| `buffer(3,5)` | [1,2,3], [6,7,8]; 4,5,9,10 không nằm trong output |

Chồng lấp **không phải làm mất bản gốc**, nhưng cùng phần tử được trình bày nhiều lần ở output. Nếu downstream gọi ghi database, tính tiền, gửi notification cho từng buffer và không xét trùng lặp, logic nghiệp vụ có thể xử lý cùng phần tử nhiều lần.

Khoảng trống cũng có hệ quả dữ liệu: `buffer(3,5)` không gửi những phần tử 4,5,9,10 xuống pipeline sau buffer. Đừng dùng overload có `skip > size` nếu yêu cầu “mọi sự kiện phải được xử lý đúng một lần”.

Với `window(size, skip)`, quy luật ranh giới tương tự, nhưng đầu ra là các inner Flux cần được tiêu thụ. Khi cửa sổ chồng lấp, một phần tử có thể được phát tới nhiều cửa sổ đang mở.

## 8. Chia theo điều kiện: `bufferUntil`, `windowUntil` và `*While`

### 8.1. Kết thúc nhóm tại phần tử thỏa điều kiện

`bufferUntil(predicate)` gom các phần tử rồi **đóng nhóm khi gặp phần tử thỏa điều kiện**, thông thường bao gồm chính phần tử gây đóng nhóm trong buffer vừa kết thúc.

~~~java
Flux.range(1, 7)
    .bufferUntil(i -> i % 3 == 0)
    .subscribe(System.out::println);
~~~

Stdout:

~~~text
[1, 2, 3]
[4, 5, 6]
[7]
~~~

`windowUntil(predicate)` có mục đích ranh giới tương ứng, nhưng cho ra `Flux<Flux<T>>`. Các overload có tham số `cutBefore` làm thay đổi **phía** của ranh giới mà phần tử triggering được đưa vào. Luôn xác minh trường hợp đúng tại boundary khi dùng trong protocol parsing hoặc sessionization.

### 8.2. Giữ nhóm trong khi predicate đúng

`bufferWhile(predicate)` chỉ gom **các dãy liên tiếp** mà predicate trả true. Những phần tử không thỏa bị bỏ khỏi các buffer output. Ví dụ:

~~~java
Flux.just(1, 3, 5, 2, 4, 6, 11, 12, 13)
    .bufferWhile(i -> i % 2 == 0)
    .subscribe(System.out::println);
~~~

Stdout:

~~~text
[2, 4, 6]
[12]
~~~

Điểm rất dễ bỏ sót: **`windowWhile` có thể tạo những window rỗng** khi liên tiếp gặp phần tử không thỏa predicate, còn `bufferWhile` **không phát buffer rỗng**. Với `windowWhile`, nếu nghiệp vụ cần bỏ window trống thì `inner.filter(...)` không áp dụng trực tiếp vì inner Flux không phải list; có thể dùng `inner.switchIfEmpty(...)` hoặc `inner.collectList().filter(list -> !list.isEmpty())`, nhưng việc chuyển thành list sẽ có chi phí bộ nhớ.

Khác với `groupBy`, cả `bufferWhile` và `windowWhile` phản ứng với **sự liên tiếp** của các phần tử. Nếu các giá trị chẵn xuất hiện ở nhiều đoạn cách nhau, output có thể là nhiều nhóm chẵn tách biệt chứ không phải một nhóm “even” xuyên suốt.

## 9. Ranh giới thời gian: khi nguồn không đều

Nguồn theo thời gian thường không phát đều. `buffer(100)` có thể chờ rất lâu để đủ 100 phần tử nếu lưu lượng thấp. Reactor có các operator kết hợp số lượng và thời gian:

~~~java
Flux<Event> input = obtainEvents();

Flux<java.util.List<Event>> batches =
    input.bufferTimeout(100, java.time.Duration.ofSeconds(2));
~~~

Đây là **snippet minh họa**, `Event` và `obtainEvents()` do ứng dụng cung cấp. `bufferTimeout(maxSize, maxTime)` tạo lô đóng khi đạt kích thước **hoặc** giới hạn thời gian, tùy điều kiện nào xảy ra theo ngữ nghĩa operator. Lô cuối có thể ít phần tử hơn mong đợi. Không viết test đòi batch có đúng 100 phần tử với nguồn phát không ổn định.

Tương tự, `windowTimeout(maxSize, maxTime)` tạo các window bên trong là Flux, không phải list. Ngoài ra còn có `buffer(Duration)`, `window(Duration)` và các overload điều khiển ranh giới bằng publisher.

Khi viết unit test phụ thuộc thời gian, nên dùng `StepVerifier.withVirtualTime(...)` và nguồn được tạo **bên trong supplier** của `withVirtualTime` để test không phải chờ đồng hồ thật. Không suy luận output theo thứ tự timer nếu pipeline có nguồn bất đồng bộ và scheduler khác nhau mà chưa kiểm soát được scheduler trong test.

**Các cảnh báo:** buffer/window theo thời gian không tự đảm bảo lịch thực thi chính xác từng mili giây dưới tải; đồng thời việc tạo nhiều cửa sổ chồng lấp theo thời gian có thể tăng overhead, bộ nhớ hoặc khiến cùng phần tử xuất hiện nhiều nơi.

## 10. `groupBy` và nguy cơ nghẽn do không tiêu thụ group

Một đặc điểm rất quan trọng của `groupBy` là các nhóm động **phải được downstream tiêu thụ** để có chỗ cho nguồn phát tiếp. Với khóa phân tán xen kẽ, một số nhóm có thể đang đợi subscriber trong khi `groupBy` giữ dữ liệu của chúng.

**Ví dụ dễ mắc lỗi:**

~~~java
Flux<Event> events = obtainEvents();

Flux<Result> results = events
    .groupBy(Event::tenantId)
    .concatMap(group -> consumeWholeGroup(group));
~~~

Đây là snippet (`Event`, `Result`, `obtainEvents`, `consumeWholeGroup` do ứng dụng định nghĩa). `concatMap` chỉ xử lý một group tại một thời điểm. Với các group dài và dữ liệu các tenant xen kẽ, group đầu tiên có thể cần thêm dữ liệu để hoàn tất nhưng upstream đã không thể gửi tiếp vì buffer của các group khác đang đầy. Pipeline có nguy cơ **treo do backpressure**, dù không có thread deadlock truyền thống.

Cách xử lý khi số group **nhỏ và đã biết giới hạn**:

~~~java
Flux<String> results = Flux.just(
        "tenant-A:1", "tenant-B:1", "tenant-A:2", "tenant-B:2"
    )
    .groupBy(s -> s.substring(0, 8))
    .flatMap(group ->
        group.collectList()
             .map(items -> group.key() + "=" + items),
        2 // đủ concurrency cho hai khóa A/B trong ví dụ
    );
~~~

Với dữ liệu vô hạn/long-lived, **không dùng `collectList()` trên mỗi group** nếu không có cơ chế đóng group: nó chờ group hoàn tất và có thể tích lũy không giới hạn. Thay vào đó, có thể xử lý từng phần tử trong group, hoặc dùng `bufferTimeout`, `windowTimeout` theo từng group rồi xử lý lô hữu hạn, đồng thời có chính sách lifecycle cho số group.

Các nguyên tắc an toàn:

1. **Cardinality:** `groupBy(event -> event.id())` trên mỗi UUID duy nhất có thể tạo gần bằng số phần tử group; áp lực bộ nhớ lớn. Chỉ group theo khóa có số lượng được kiểm soát.
2. **Consume promptly:** ngay khi group được emit, cần có subscriber tiêu thụ nội dung. `flatMap` thường hữu ích hơn `concatMap` khi các khóa xen kẽ; concurrency phải đủ so với mẫu dữ liệu và số group có thể đồng thời mở.
3. **Prefetch không thay thế tiêu thụ:** tăng prefetch/queue chỉ trì hoãn điểm nghẽn và có thể tốn thêm RAM.
4. **Thứ tự:** `flatMap` có thể trộn kết quả của các group. Nếu cần thứ tự toàn cục của nguồn, phải thiết kế riêng; `groupBy` vốn đã sắp xếp lại luồng theo khóa.
5. **Unicast group:** từng `GroupedFlux` gắn với vòng đời nguồn và được thiết kế cho một subscriber. Không tự `retry()`/`repeat()` một inner group như một cold Flux có thể subscribe lại tùy ý.
6. **Nguồn không kết thúc:** group thường tiếp tục mở đến khi nguồn hoàn thành hoặc bị hủy; nếu cần nhóm theo ngày/phiên, một key đơn thuần không biểu diễn ranh giới thời gian. Có thể dùng key kèm bucket thời gian có kiểm soát hoặc windowing thích hợp.

Nếu có hàng nghìn/millions khóa không giới hạn, cân nhắc kiến trúc partitioning/queue chuyên dụng, downstream store có khả năng xử lý theo key, hoặc kiểm soát số nhóm đang hoạt động và policy loại bỏ; đừng dựa vào `groupBy` như bộ lưu trữ vĩnh viễn tất cả khóa.

## 11. Backpressure: demand ở downstream dùng đơn vị gì?

Trong Reactive Streams, `request(n)` cấp quyền cho n **tín hiệu `onNext` tại chính subscription đó**. Sau khi nhóm hóa, một phần tử downstream có thể đại diện cho nhiều phần tử upstream:

- Sau `buffer(10)`, một `onNext` downstream thường là **một `List<T>` gồm tối đa 10 phần tử**; downstream `request(2)` có thể khiến upstream cần cấp tới 20 phần tử để đáp ứng hai list đủ 10.
- Sau `window(10)`, một `onNext` của luồng **ngoài** là một inner Flux. Inner Flux lại có demand riêng từ subscriber tiêu thụ window.
- Sau `groupBy(key)`, một `onNext` của luồng **ngoài** là một `GroupedFlux` cho một key. Các phần tử bên trong mỗi group được điều tiết riêng, và key xuất hiện sau có thể chờ group được tiêu thụ.

**Tách quota với bộ nhớ:** `request(2)` ở `Flux<List<T>>` không bảo đảm tại mọi thời điểm chỉ có hai phần tử nguồn trong RAM. Các buffer, queue, prefetch và operator con có trạng thái riêng. Khi xử lý nguồn lớn/nhanh, đo lượng phần tử/batch đang tồn đọng thực tế và cấu hình kích thước, concurrency, scheduler phù hợp.

Đặt `doOnRequest(n -> System.out.println("requested " + n))` trước và sau operator để quan sát sự thay đổi quota. Các log là kích thước **mỗi lần request** ở chặng ấy, không trực tiếp là pending demand toàn pipeline.

## 12. Ứng dụng trong Spring WebFlux

### 12.1. Gom sự kiện để gửi cho service lưu theo lô

Một service dùng API reactive có thể gom 100 sự kiện mỗi batch để giảm số lần gọi tới một service khác:

~~~java
public Flux<SaveResult> saveInBatches(Flux<Event> events) {
    return events
        .bufferTimeout(100, Duration.ofSeconds(1))
        .filter(batch -> !batch.isEmpty())
        .concatMap(batch -> reactiveRepository.saveBatch(batch));
}
~~~

Đây là **snippet nghiệp vụ**: `Event`, `SaveResult`, `reactiveRepository` và method `saveBatch` phải được ứng dụng định nghĩa; cần import `Flux` và `Duration`. Giả sử `saveBatch(batch)` trả `Publisher<SaveResult>`, `concatMap` xử lý **các batch theo thứ tự, không chạy song song**. Dùng `flatMap(..., concurrency)` khi backend chấp nhận batch song song và hệ thống đã có giới hạn cạnh tranh/nhu cầu thứ tự rõ ràng.

**Không tự giả định batch là transaction:** DB transaction do repository/driver/quy tắc Spring Transaction quản lý; list 100 phần tử không tự tạo một transaction.

Nếu repository là JDBC đồng bộ, lời gọi JDBC phải được hoãn và chạy ở scheduler phù hợp thay vì chặn event-loop:

~~~java
public Flux<SaveResult> saveLegacy(Flux<Event> events) {
    return events
        .buffer(100)
        .concatMap(batch -> Mono
            .fromCallable(() -> legacyRepository.saveBatchBlocking(batch))
            .subscribeOn(Schedulers.boundedElastic())
        );
}
~~~

Đây cũng là snippet; `Mono`, `Schedulers` và các kiểu của ứng dụng cần được import/định nghĩa. `boundedElastic` **cách ly blocking**, không khiến JDBC trở thành I/O non-blocking. Phải có timeout và giới hạn connection pool phù hợp.

### 12.2. Chia sự kiện thành cửa sổ để xử lý luồng

~~~java
public Flux<WindowResult> processWindows(Flux<Event> events) {
    return events
        .windowTimeout(50, Duration.ofSeconds(2))
        .concatMap(window -> processOneWindow(window));
}
~~~

Đây là snippet; `processOneWindow` nhận `Flux<Event>` và trả `Publisher<WindowResult>` theo hợp đồng ứng dụng. Khác `bufferTimeout`, service phía sau có thể xử lý các phần tử trong window như một stream thay vì phải chờ có một list đầy đủ. Nếu `processOneWindow` tự `collectList()` thì lợi thế streaming giảm đi và nó lại tích lũy dữ liệu.

### 12.3. Phân loại theo khóa nghiệp vụ

~~~java
Flux<HandledEvent> handled = events
    .groupBy(Event::category)
    .flatMap(group ->
        group.concatMap(event -> handleCategory(group.key(), event)),
        4
    );
~~~

Đây là snippet, `HandledEvent` và `handleCategory` do ứng dụng cung cấp. Giả sử chỉ có **tối đa bốn category** đồng thời, `flatMap(..., 4)` cho phép mở group song song; `concatMap` bên trong giữ thứ tự phần tử **trong từng group**. Kết quả từ **các group khác nhau** vẫn có thể xen kẽ. Nếu số category thực tế lớn hơn giới hạn và luồng chứa dữ liệu xen kẽ, cần xem xét lại concurrency/backpressure để tránh treo.

## 13. Kiểm thử bằng Reactor Test

Dùng `StepVerifier` để xác minh không mất phần tử khi không có cấu hình `skip`, cũng như hành vi của predicate.

Thay khối `dependencies` của `build.gradle` ở mục 6 bằng khối sau, và bổ sung `test` (không thêm một dependencies trùng lặp):

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
    testImplementation 'io.projectreactor:reactor-test:3.8.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/BatchingTest.java`:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BatchingTest {
    @Test
    void bufferEmitsFinalPartialBatch() {
        StepVerifier.create(Flux.range(1, 7).buffer(3))
            .expectNext(List.of(1, 2, 3))
            .expectNext(List.of(4, 5, 6))
            .expectNext(List.of(7))
            .verifyComplete();
    }

    @Test
    void windowIsAnInnerPublisher() {
        StepVerifier.create(
                Flux.range(1, 5)
                    .window(2)
                    .concatMap(window -> window.collectList())
            )
            .expectNext(List.of(1, 2))
            .expectNext(List.of(3, 4))
            .expectNext(List.of(5))
            .verifyComplete();
    }

    @Test
    void bufferWhileIgnoresNonmatchingElements() {
        StepVerifier.create(
                Flux.just(1, 3, 5, 2, 4, 6, 11, 12, 13)
                    .bufferWhile(i -> i % 2 == 0)
            )
            .expectNext(List.of(2, 4, 6))
            .expectNext(List.of(12))
            .verifyComplete();
    }

    @Test
    void groupBySeparatesInterleavedKeys() {
        StepVerifier.create(
                Flux.just("A1", "B1", "A2")
                    .groupBy(s -> s.substring(0, 1))
                    .flatMap(group ->
                        group.collectList()
                             .map(items -> group.key() + "=" + items)
                    )
                    .sort()
            )
            .expectNext("A=[A1, A2]")
            .expectNext("B=[B1]")
            .verifyComplete();
    }
}
~~~

Chạy `gradle test`. Kỳ vọng cả bốn test PASS. Test cố ý dùng nguồn hữu hạn, đồng bộ và `sort()` khi so sánh kết quả groupBy; không phụ thuộc thứ tự concurrent emission. Với bài toán theo thời gian, dùng virtual time nếu cần test sự đóng nhóm theo timeout.

## 14. Chọn operator từ yêu cầu nghiệp vụ

| Yêu cầu | Lựa chọn ban đầu | Cần kiểm tra thêm |
| --- | --- | --- |
| Gửi 100 bản ghi/lần, chấp nhận list | `buffer(100)` | Nếu nguồn chậm thì batch có thể chờ lâu |
| Gửi tối đa 100 bản ghi hoặc mỗi 2 giây | `bufferTimeout(100, Duration.ofSeconds(2))` | Batch cuối nhỏ; timeout/scheduler |
| Cần xử lý từng đoạn 100 phần tử như stream | `window(100)` | Phải subscribe/tiêu thụ inner Flux |
| Chia theo phiên 5 giây | `window(Duration.ofSeconds(5))` | Thời gian, empty windows, resource |
| Gộp theo dấu kết thúc bản tin | `bufferUntil(isTerminator)` hoặc `windowUntil(isTerminator)` | Tính đúng việc giữ/chuyển phần tử ranh giới |
| Chỉ lấy các dãy liên tiếp thỏa predicate | `bufferWhile(predicate)`/`windowWhile(predicate)` | Phần tử không thỏa; window rỗng |
| Nhóm mọi phần tử theo customerId/tenantId | `groupBy(key)` | Cardinality, số group hoạt động, concurrency |
| Chỉ gom các đoạn có cùng trạng thái liên tiếp | `bufferUntilChanged(keyFn)`/`windowUntilChanged(keyFn)` | Có thể nhiều đoạn trùng khóa ở vị trí khác nhau |
| Muốn chia nhóm chồng lấp | `buffer(size, skip)` với `size > skip` | Phần tử bị lặp ở output |
| Muốn lấy mẫu bằng khoảng trống | `buffer(size, skip)` với `size < skip` | Chủ động bỏ phần tử; không dùng khi cần toàn vẹn dữ liệu |

Đặt câu hỏi trước khi chọn: “Đầu ra cần **List** hay **Flux con**?”, “Tiêu chí là **thời gian/kích thước** hay **khóa**?”, “Các nhóm có được chồng lấp/bỏ phần tử không?”, “Nguồn có thể vô hạn không?”, “Có bao nhiêu nhóm đồng thời?”, “Downstream có tiêu thụ được tất cả group không?”.

## 15. Các lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Tưởng `window(5)` trả list | Sai kiểu `Flux<Flux<T>>` | Subscribe inner Flux; chỉ `collectList` khi thực sự cần |
| Dùng `buffer(100)` trên nguồn phát thưa và không bao giờ complete | Batch có thể không xuất hiện | Cân nhắc `bufferTimeout` và hợp đồng kết thúc |
| Dùng `buffer(5,3)` rồi giả định mỗi item xuất hiện đúng một lần | Duplicated item trong các buffer | Dùng `buffer(5)` hoặc `buffer(5,5)` nếu muốn nhóm rời |
| Dùng `buffer(3,5)` nhưng yêu cầu toàn vẹn | Các phần tử trong khoảng trống bị bỏ | Chọn `skip == size` |
| Dùng `groupBy` để tách **đoạn liên tiếp** mang một trạng thái | Các đoạn không liền nhau cùng khóa bị gộp vào một group | Dùng operator `UntilChanged` hoặc predicate boundary |
| `groupBy` theo ID duy nhất mỗi event | Quá nhiều group/queue | Giảm cardinality, dùng kiến trúc partition có giới hạn |
| `groupBy(...).concatMap(group -> group.collectList())` trên luồng xen kẽ/dài | Có thể treo vì không drain group khác | Consume group phù hợp, concurrency đủ, không collect vô hạn |
| Tưởng `flatMap` giữ thứ tự toàn cục | Kết quả group có thể xen kẽ | Chỉ giữ thứ tự nơi cần, giới hạn concurrency |
| Dùng `collectList()` cho inner group không bao giờ kết thúc | Không emit summary; có thể tăng RAM | Xử lý streaming hoặc buffer theo ranh giới hữu hạn |
| Tưởng `buffer` là database transaction | Gom list không tự tạo transaction | Thiết kế repository/transaction boundary riêng |
| Tưởng mọi window đều có ít nhất một item | `windowWhile` có thể có window rỗng | Xử lý empty-window rõ ràng |
| Chạy `block()` trong handler WebFlux | Chặn event-loop, giảm thông lượng | Return Flux/Mono; ghép qua operator không chặn |
| Không nghĩ đến backpressure ở inner Flux | Queue giữ dữ liệu và pipeline đình trệ | Subscribe/drain inner đúng cách; theo dõi demand/prefetch |

## 16. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `Flux.range(1, 7).buffer(3)` phát mấy list, độ dài lần lượt bao nhiêu?

**Đáp án:** Ba list, độ dài 3, 3 và 1: `[1,2,3]`, `[4,5,6]`, `[7]`.

**Câu 2.** `Flux.range(1, 10).buffer(5, 3)` có làm trùng phần tử không?

**Đáp án:** Có. Các buffer bắt đầu ở 1, 4, 7, 10; phần tử 4–5, 7–8 và 10 có thể xuất hiện ở nhiều buffer tùy vị trí chồng lấp; output là `[1..5]`, `[4..8]`, `[7..10]`, `[10]`.

**Câu 3.** Vì sao `Flux<Flux<T>>` từ `window` không tương đương `Flux<List<T>>` từ `buffer`?

**Đáp án:** Inner Flux là nguồn có vòng đời/demand riêng, có thể phát các phần tử trong thời gian window còn mở. List là collection đã tích lũy và phát như một phần tử downstream.

**Câu 4.** Với input `A1, B1, A2, B2` và `groupBy(prefix)`, có bao nhiêu group A?

**Đáp án:** Một group A chứa A1 và A2, mặc dù B1 nằm xen giữa.

**Câu 5.** Tại sao `groupBy(key).concatMap(g -> g.collectList())` có nguy cơ treo trên nguồn nhiều key xen kẽ?

**Đáp án:** `concatMap` chỉ tiêu thụ một group, còn `groupBy` có thể phải giữ phần tử của các group khác. Khi buffer/prefetch đầy, upstream không thể phát những phần tử cần thiết để group đang chờ hoàn tất.

**Câu 6.** Đang gom `buffer(100)` nhưng nguồn có thể chỉ phát 3 phần tử trong một giờ và không complete, làm sao phát batch sớm hơn?

**Đáp án:** Cân nhắc `bufferTimeout(100, Duration.ofSeconds(...))`; đồng thời quyết định rõ cho phép batch dưới 100 phần tử và cách xử lý khi nguồn im lặng.

**Câu 7.** Khi nào nên dùng `groupBy`, khi nào dùng `bufferUntilChanged`?

**Đáp án:** `groupBy` nếu muốn cùng khóa từ mọi vị trí được đưa vào cùng một nhóm hoạt động; `bufferUntilChanged` nếu muốn chia theo **những đoạn liên tiếp** có cùng khóa, nên cùng khóa có thể sinh nhiều đoạn.

## 17. Ghi nhớ và tham khảo

- **`buffer` phát collection, `window` phát luồng con, `groupBy` phát luồng con theo khóa.**
- `size == skip` tạo nhóm liền kề, `size > skip` tạo chồng lấp, `size < skip` bỏ khoảng.
- Ranh giới predicate/thời gian ảnh hưởng lúc hoàn thành; `windowWhile` có thể có window rỗng, còn `bufferWhile` không phát list rỗng.
- Inner Flux/GroupedFlux **phải được tiêu thụ**; không dùng `collectList()` không giới hạn cho nguồn vô hạn.
- `groupBy` phù hợp với **số khóa thấp/vừa có thể kiểm soát**; kết hợp concurrency thấp và khóa xen kẽ dễ bị nghẽn do backpressure.
- Trong WebFlux, không dùng `block()` ở reactive request handler; lựa chọn batching không thay thế cơ chế non-blocking I/O và transaction.

Tài liệu chính thức:

1. [Project Reactor — Three Sorts of Batching](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-three-sorts-batching.html): so sánh chi tiết `groupBy`, `window`, `buffer`, các ví dụ chồng lấp và warning về hang do `groupBy`.
2. [Project Reactor — Which Operator Do I Need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): tra cứu operator theo tình huống, trong đó có group/window/buffer.
3. [Flux API Reference](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): overload và contract của `buffer`, `window`, `groupBy`.
4. [Reactor — Backpressure and Request Reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): demand qua các operator.
5. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): dùng Reactor trong HTTP stack Spring.
