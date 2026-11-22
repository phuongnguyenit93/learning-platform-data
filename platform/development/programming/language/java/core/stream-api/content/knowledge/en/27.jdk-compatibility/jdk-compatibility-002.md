# Các bổ sung Java 9: ofNullable, iterate, takeWhile và dropWhile

Trong chương **Khả năng tương thích JDK** của **Java Stream API**, thay đổi phiên bản Java có ảnh hưởng trực tiếp đến cách viết pipeline. Java 8 giới thiệu Stream và những thao tác quen thuộc như `filter`, `map`, `flatMap`, `reduce`, `collect`; **Java 9 bổ sung bốn công cụ quan trọng** giúp xử lý phần tử có thể rỗng, sinh dãy có điểm dừng và làm việc với **tiền tố** của một Stream.

Bốn bổ sung trong bài này là:

1. `Stream.ofNullable(value)`: tạo Stream gồm **một** phần tử nếu giá trị khác `null`, hoặc Stream rỗng nếu là `null`.
2. `Stream.iterate(seed, hasNext, next)`: sinh dãy tuần tự theo quy tắc chuyển trạng thái, **có điều kiện kết thúc**.
3. `takeWhile(predicate)`: trên Stream có thứ tự, **lấy tiền tố dài nhất** gồm những phần tử liên tiếp thỏa predicate.
4. `dropWhile(predicate)`: trên Stream có thứ tự, **bỏ tiền tố dài nhất** gồm những phần tử liên tiếp thỏa predicate, rồi giữ phần còn lại.

Chúng ta sẽ phân biệt chúng với `Stream.of`, `filter`, `limit` và `skip`; triển khai ví dụ **chạy được trên Java 9**; phân tích các bẫy với nguồn không có encounter order, nguồn vô hạn, xử lý song song và nâng/hạ phiên bản JDK.

## 1. Bản đồ phiên bản: những API nào có từ Java 9?

| API | Phiên bản đầu tiên | Ý nghĩa chính |
| --- | --- | --- |
| `Stream.ofNullable(T)` | **Java 9** | Chuyển một giá trị có thể `null` thành Stream có 0 hoặc 1 phần tử |
| `Stream.iterate(T, Predicate, UnaryOperator)` | **Java 9** | Sinh dãy có điều kiện kiểm tra trước khi phát phần tử |
| `IntStream.iterate(seed, hasNext, next)` và các biến thể primitive | **Java 9** | Sinh dãy primitive có điểm dừng |
| `Stream.takeWhile(Predicate)` | **Java 9** | Lấy tiền tố theo điều kiện |
| `Stream.dropWhile(Predicate)` | **Java 9** | Bỏ tiền tố theo điều kiện |
| `Optional.stream()` | **Java 9** | Chuyển Optional thành Stream 0 hoặc 1 phần tử; liên quan đến `ofNullable` |
| `Stream.iterate(seed, next)` | Java 8 | Sinh dãy không có điều kiện dừng ngay trong overload |
| `Stream.of`, `filter`, `limit`, `skip` | Java 8 | Những thao tác nền tảng để so sánh |

**Điểm cần phân biệt:** `Stream.toList()` chỉ có từ **Java 16**, không phải Java 9. Vì vậy, phần chương trình Java 9 có thể biên dịch trong bài này dùng `collect(Collectors.toList())`. `List.of(...)` có từ **Java 9**, nên được phép xuất hiện trong ví dụ nhắm Java 9. Nếu mã nguồn của dự án buộc tương thích Java 8, cần thay cả những API Java 9 này bằng giải pháp tương đương.

Bài viết bàn về **API chuẩn trong `java.util.stream`**. Nó không cần thêm thư viện ngoài hay bật tính năng preview, nhưng dự án phải biên dịch và chạy trên môi trường hỗ trợ các API tương ứng.

## 2. Stream.ofNullable: null trở thành 0 phần tử, không phải một phần tử null

Trước Java 9, một đoạn mã thường phải rẽ nhánh:

~~~java
String code = maybeCode();

Stream<String> codes = code == null
        ? Stream.empty()
        : Stream.of(code);
~~~

Từ Java 9:

~~~java
Stream<String> codes = Stream.ofNullable(code);
~~~

Hợp đồng của `Stream.ofNullable(x)` rất cụ thể:

| Giá trị `x` | Phần tử trong Stream | `count()` |
| --- | --- | ---: |
| `"JAVA"` | Một phần tử `"JAVA"` | 1 |
| `""` | Một phần tử chuỗi rỗng | 1 |
| `null` | Không có phần tử | 0 |
| Đối tượng bất kỳ khác `null` | Một phần tử là đối tượng đó | 1 |

Ví dụ tối giản:

~~~java
import java.util.stream.Stream;

System.out.println(Stream.ofNullable("Java").count()); // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
System.out.println(Stream.ofNullable("").count()); // 1
~~~

Một `String` rỗng **không phải** `null`; `ofNullable` không có chức năng tự kiểm tra chuỗi rỗng, độ dài, mã hợp lệ hoặc nội dung nghiệp vụ.

### ofNullable khác map và filter như thế nào?

Giả sử một bản ghi có trường email tùy chọn. Với `map` đơn thuần:

~~~java
List<String> emails = users.stream()
        .map(User::email)
        .collect(Collectors.toList());
~~~

Nếu `email()` trả `null` thì Stream vẫn có **một phần tử null** tương ứng với người dùng đó, trừ khi bước khác loại bỏ.

Với `ofNullable` và `flatMap`:

~~~java
List<String> emails = users.stream()
        .flatMap(user -> Stream.ofNullable(user.email()))
        .collect(Collectors.toList());
~~~

Mỗi người dùng sinh **0 hoặc 1 email**; những trường hợp `email == null` không đưa phần tử vào downstream.

Một cách biểu đạt gần tương đương:

~~~java
List<String> emails = users.stream()
        .map(User::email)
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toList());
~~~

Chọn cách nào tùy mục đích:

- `map(...).filter(Objects::nonNull)` dễ hiểu khi đã có một bước biến đổi tổng quát và cần lọc null.
- `flatMap(user -> Stream.ofNullable(...))` diễn đạt gọn việc **một bản ghi có thể không tạo phần tử đầu ra**.
- `Optional.ofNullable(value).stream()` cũng chuyển 0/1 phần tử và có từ Java 9, hữu ích nếu hệ thống vốn đang dùng `Optional`; không nhất thiết tạo `Optional` mới chỉ để dùng `ofNullable`.

**Không dùng `ofNullable` để âm thầm bỏ dữ liệu thiếu bắt buộc.** Nếu email, mã khách hay mã giao dịch phải tồn tại, hãy kiểm tra và báo lỗi theo hợp đồng nghiệp vụ trước khi thu thập.

## 3. Ví dụ thực tế: gắn thông tin tùy chọn cho dữ liệu đầu ra

Giả sử mỗi sự kiện có thể có hoặc không có trace ID:

~~~java
final class Event {
    final String service;
    final String traceId;

    Event(String service, String traceId) {
        this.service = service;
        this.traceId = traceId;
    }
}
~~~

Ta chỉ cần danh sách trace ID hiện có:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Event> events = Arrays.asList(
        new Event("auth", "T-01"),
        new Event("search", null),
        new Event("billing", "T-03")
);

List<String> traceIds = events.stream()
        .flatMap(event -> Stream.ofNullable(event.traceId))
        .collect(Collectors.toList());

System.out.println(traceIds); // [T-01, T-03]
~~~

`flatMap` làm phẳng mỗi Stream con do `ofNullable` tạo ra, nên các bản ghi không có trace ID không chiếm vị trí trong danh sách kết quả. Việc mất vị trí là **chủ đích** ở đây; nếu cần bảo toàn đúng một kết quả cho mỗi sự kiện, dùng DTO có trường nullable hoặc `Optional` trong đối tượng kết quả thay vì bỏ phần tử.

**Lưu ý về nguồn:** `List.of` không chấp nhận **phần tử danh sách** là `null`, nhưng một đối tượng `Event` bên trong danh sách vẫn có thể có `traceId = null`. Ví dụ dùng `Arrays.asList` để minh họa; danh sách các Event đều không `null`.

## 4. iterate: từ chuỗi sinh không dừng đến chuỗi có điều kiện dừng

Java 8 cung cấp:

~~~java
Stream<T> iterate(T seed, UnaryOperator<T> next)
~~~

Ví dụ:

~~~java
import java.util.stream.IntStream;

int total = IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .sum();

System.out.println(total); // 15
~~~

Overload hai tham số sinh dãy `1, 2, 3, ...` mà bản thân nguồn **không có một điều kiện kết thúc hữu hạn được khai báo**. `limit(5)` là thao tác trung gian giúp terminal `sum()` chỉ cần năm số đầu.

Java 9 bổ sung overload:

~~~java
Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next)
~~~

Với primitive stream, có các overload tương ứng của `IntStream`, `LongStream` và `DoubleStream`. Ví dụ:

~~~java
int total = IntStream.iterate(
                1,
                n -> n <= 5,
                n -> n + 1)
        .sum();

System.out.println(total); // 15
~~~

Dãy ở đây có quy tắc **kiểm tra trước khi phát**:

~~~text
seed = 1
hasNext(1) = true  -> phát 1
next(1) = 2
hasNext(2) = true  -> phát 2
...
hasNext(5) = true  -> phát 5
next(5) = 6
hasNext(6) = false -> kết thúc, KHÔNG phát 6
~~~

Nếu `hasNext(seed)` đã là `false`, Stream **rỗng ngay từ đầu**.

### Điều kiện dừng là hasNext, không phải filter

~~~java
import java.util.stream.IntStream;

int[] numbers = IntStream.iterate(
        10,
        n -> n < 10,
        n -> n + 1
).toArray();

System.out.println(numbers.length); // 0
~~~

`hasNext` xác định **có tiếp tục sinh phần tử nữa không**, khác với `filter` chỉ quyết định **giữ hay loại một phần tử đã được sinh ra**. Nếu chỉ áp dụng `filter(n -> n < 10)` lên một nguồn vô hạn đi mãi lên phía trên 10, việc tìm tất cả đầu ra bằng `collect` vẫn có thể không kết thúc.

### Sai lầm ở ranh giới

~~~java
IntStream.iterate(1, n -> n < 5, n -> n + 1)
// Phát 1, 2, 3, 4; KHÔNG có 5.

IntStream.iterate(1, n -> n <= 5, n -> n + 1)
// Phát 1, 2, 3, 4, 5.
~~~

Chọn `<` hay `<=` theo hợp đồng khoảng nửa mở/đóng của bài toán. Đừng dùng `peek` hoặc in log để suy ra thứ tự thực hiện hasNext/next trên pipeline song song.

## 5. iterate với LocalDate: sinh lịch theo khoảng ngày

Một ví dụ thực tế là tạo các ngày liên tiếp mà không cần vòng lặp ngoài Stream:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

LocalDate start = LocalDate.of(2026, 11, 15);
LocalDate endExclusive = LocalDate.of(2026, 11, 19);

List<LocalDate> days = Stream.iterate(
                start,
                day -> day.isBefore(endExclusive),
                day -> day.plusDays(1))
        .collect(Collectors.toList());

System.out.println(days);
// [2026-11-15, 2026-11-16, 2026-11-17, 2026-11-18]
~~~

Tên `endExclusive` nói rõ rằng ngày 19 **không** nằm trong kết quả. Nếu muốn cả ngày 19, điều kiện có thể là `!day.isAfter(endInclusive)` với biến cuối `endInclusive`.

`LocalDate` là đối tượng bất biến; mỗi lần `plusDays(1)` tạo ngày mới. Điều này tránh việc chia sẻ một đối tượng lịch mutable rồi cập nhật qua nhiều phần tử.

### Không nhất thiết nhanh hơn range hoặc vòng lặp

Đối với dãy số nguyên đơn giản, `IntStream.range(0, n)` hoặc `rangeClosed` thường biểu đạt phạm vi tốt hơn và có nguồn Spliterator dễ chia:

~~~java
int[] values = IntStream.rangeClosed(1, 5).toArray();
// [1, 2, 3, 4, 5]
~~~

`iterate` đặc biệt phù hợp khi **phần tử kế tiếp được tính từ trạng thái trước** mà không phải khoảng số nguyên đơn giản: ngày, phiên bản tăng dần, trạng thái thuật toán, tiến độ một quy trình hữu hạn. Một dãy phụ thuộc phần tử trước thường khó song song hóa hiệu quả hơn nguồn chia được theo chỉ số.

## 6. takeWhile: lấy tiền tố liên tiếp, không phải lọc tất cả phần tử đúng

`takeWhile(predicate)` là intermediate operation có từ Java 9. Trên **Stream có encounter order**, nó giữ **tiền tố dài nhất** của những phần tử liên tiếp thỏa predicate; gặp phần tử đầu tiên không thỏa thì không tiếp tục lấy phần tử phía sau vào kết quả.

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(prefix); // [2, 4]
~~~

Dù `8` và `10` cũng là số chẵn, chúng **không xuất hiện** vì phần tử `7` đã làm tiền tố dừng lại.

So sánh trực tiếp với `filter`:

~~~java
List<Integer> allEven = values.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(allEven); // [2, 4, 8, 10]
~~~

| Thao tác | Phát phần tử nào? | Với `[2,4,7,8,10]`, predicate chẵn |
| --- | --- | --- |
| `filter(p)` | Mọi phần tử thỏa `p` trong toàn bộ nguồn | `[2,4,8,10]` |
| `takeWhile(p)` | Các phần tử thỏa `p` **liên tiếp ở đầu** | `[2,4]` |
| `limit(2)` | Hai phần tử đầu, bất kể điều kiện | `[2,4]` trong ví dụ; khác về bản chất |

**Không thay `filter` bằng `takeWhile` chỉ vì muốn dừng sớm**, trừ khi bài toán thật sự yêu cầu tiền tố hoặc đã chứng minh sau phần tử không hợp lệ đầu tiên không còn phần tử cần lấy.

## 7. takeWhile trong dữ liệu đã sắp xếp: phân đoạn theo mốc thời gian

Một tình huống hữu ích: log/sự kiện đã được sắp **tăng dần theo timestamp**, và chỉ cần sự kiện trước một mốc.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;

final class DatedEvent {
    final LocalDate date;
    final String code;

    DatedEvent(LocalDate date, String code) {
        this.date = date;
        this.code = code;
    }
}

List<DatedEvent> events = List.of(
        new DatedEvent(LocalDate.of(2026, 11, 15), "A"),
        new DatedEvent(LocalDate.of(2026, 11, 16), "B"),
        new DatedEvent(LocalDate.of(2026, 11, 18), "C")
);

LocalDate cutoff = LocalDate.of(2026, 11, 17);

List<String> beforeCutoff = events.stream()
        .takeWhile(e -> e.date.isBefore(cutoff))
        .map(e -> e.code)
        .collect(Collectors.toList());

System.out.println(beforeCutoff); // [A, B]
~~~

Vì sự kiện có thứ tự thời gian tăng dần, sau khi gặp ngày 18 (không trước cutoff), ta biết **mọi phần tử phía sau cũng không thỏa**, nên có thể dừng việc lấy tiền tố.

Nhưng nếu nguồn **không được sắp xếp**:

~~~text
2026-11-15 -> A
2026-11-18 -> C
2026-11-16 -> B
~~~

`takeWhile(e -> e.date.isBefore(cutoff))` chỉ thu `A`, **bỏ qua cả B** dù B trước mốc. Trong trường hợp cần **mọi sự kiện trước cutoff** từ nguồn không sắp xếp, dùng `filter` thay vì `takeWhile`.

Có thể `sorted(comparator)` trước `takeWhile` nếu dữ liệu chưa có thứ tự, nhưng `sorted` là thao tác có trạng thái, có thể cần vật hóa toàn bộ phần tử để sắp xếp. Với nguồn lớn, giải pháp đúng thường là lấy nguồn **đã sắp xếp từ nơi lưu trữ** hoặc dùng hệ thống truy vấn theo chỉ mục thời gian.

## 8. dropWhile: bỏ tiền tố, giữ nguyên phần còn lại

`dropWhile(predicate)` là đối ứng của `takeWhile` trên Stream có thứ tự: bỏ những phần tử **liên tiếp từ đầu** còn thỏa predicate. Khi gặp phần tử đầu tiên không thỏa, nó giữ phần tử đó **và các phần tử sau**, kể cả khi những phần tử sau lại thỏa predicate.

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> suffix = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(suffix); // [7, 8, 10]
~~~

Phần tử `7` là điểm chuyển:

~~~text
Nguồn:      [2, 4, | 7, 8, 10]
dropWhile:   bỏ   | giữ tất cả từ 7
Kết quả:          [7, 8, 10]
~~~

So sánh với `filter(n -> n % 2 != 0)`:

~~~java
List<Integer> oddOnly = values.stream()
        .filter(n -> n % 2 != 0)
        .collect(Collectors.toList());

System.out.println(oddOnly); // [7]
~~~

Hai kết quả khác nhau rất lớn. `dropWhile` không phải phép “loại mọi số chẵn”.

### Ví dụ thực tế: bỏ phần header liên tiếp ở đầu tệp

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> lines = Arrays.asList(
        "# exported-by=system",
        "# format=csv",
        "id,name",
        "1,Lan",
        "# comment in body",
        "2,An"
);

List<String> body = lines.stream()
        .dropWhile(line -> line.startsWith("#"))
        .collect(Collectors.toList());

System.out.println(body);
// [id,name, 1,Lan, # comment in body, 2,An]
~~~

Đúng với yêu cầu **bỏ các dòng chú thích ở đầu**, không phải bỏ mọi chú thích. Dòng `# comment in body` vẫn được giữ vì nó nằm sau dòng `id,name` đầu tiên không thỏa predicate.

Nếu định dạng file cho phép comment ở **mọi vị trí**, hãy dùng `filter(line -> !line.startsWith("#"))`; đó là bài toán khác.

## 9. Các trường hợp biên của takeWhile và dropWhile

Với Stream có thứ tự, xét predicate `p`:

| Dãy đầu vào so với `p` | `takeWhile(p)` | `dropWhile(p)` |
| --- | --- | --- |
| Stream rỗng | Rỗng | Rỗng |
| Phần tử đầu tiên không thỏa | Rỗng | Giữ toàn bộ |
| Tất cả phần tử đều thỏa | Giữ toàn bộ | Rỗng |
| Một số phần tử đầu thỏa, sau đó một phần tử không thỏa | Giữ đúng tiền tố thỏa | Giữ từ phần tử không thỏa đầu tiên đến hết |

Đối với một Stream hữu hạn có thứ tự, dữ liệu có thể được tách thành **hai phần theo cùng predicate**: tiền tố mà `takeWhile` giữ và hậu tố mà `dropWhile` giữ. Tuy nhiên, **không thể gọi hai terminal operation trên cùng một đối tượng Stream đã bị tiêu thụ**. Nếu muốn lấy cả hai phần, cần tạo hai Stream mới từ nguồn có thể duyệt lại, hoặc tự triển khai phân đoạn trong một lượt duyệt.

Không nên thử:

~~~java
Stream<Integer> stream = values.stream();

List<Integer> prefix = stream.takeWhile(p).collect(Collectors.toList());
// Không thể tiếp tục dùng lại stream:
List<Integer> suffix = stream.dropWhile(p).collect(Collectors.toList());
~~~

Cả hai thao tác là intermediate operation nhưng terminal `collect` đã tiêu thụ Stream thứ nhất, do đó tái sử dụng cùng `stream` không hợp lệ.

## 10. Encounter order quyết định ý nghĩa của takeWhile/dropWhile

**Điểm dễ sai nhất khi dùng Java 9:** ý nghĩa “tiền tố dài nhất” chỉ được bảo đảm khi Stream có **encounter order**.

Nguồn thường có encounter order:

- `List.stream()` và `List.parallelStream()`.
- `IntStream.range(...)` hoặc `LongStream.range(...)`.
- Những nguồn có `Spliterator.ORDERED` đúng hợp đồng.

Nguồn có thể **không** có encounter order:

- `HashSet.stream()`, theo hợp đồng không bảo đảm một thứ tự duyệt nhất quán.
- Stream đã chủ động gọi `unordered()`.
- Một số Spliterator hoặc collector tùy chỉnh không công bố `ORDERED`.

Với Stream **unordered**, Java API cho phép `takeWhile` chọn **một tập con bất kỳ của các phần tử thỏa predicate**, không buộc phải là tiền tố duy nhất vì không có thứ tự được định nghĩa. `dropWhile` có thể bỏ một tập con bất kỳ của các phần tử thỏa predicate; những phần tử không thỏa vẫn phải được giữ.

~~~java
import java.util.Set;

Set<Integer> set = Set.of(2, 4, 7, 8, 10);

List<Integer> output = set.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

// KHÔNG được khẳng định output luôn là [2, 4]
// hoặc luôn chứa toàn bộ các số chẵn.
~~~

Đây không phải lỗi ngẫu nhiên; đó là phần **được phép của hợp đồng API**. Dùng `takeWhile`/`dropWhile` cho bài toán “bản ghi trước/sau mốc” cần **thứ tự rõ ràng**, thông thường là nguồn sắp theo khóa hoặc timestamp.

### unordered() không phải nút tối ưu vô hại

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> result = values.parallelStream()
        .unordered()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

`unordered()` tuy có thể giảm một số ràng buộc điều phối, nhưng đồng thời **bỏ bảo đảm lấy tiền tố theo thứ tự danh sách**. Chỉ dùng khi nghiệp vụ không quan tâm tiền tố; nếu chỉ cần mọi phần tử thỏa predicate, `filter` mới là thao tác diễn đạt đúng ý định.

## 11. Stream song song và chi phí duy trì tiền tố

`takeWhile` và `dropWhile` có thể sử dụng trong pipeline song song, nhưng cần đánh giá **đúng ngữ nghĩa trước, hiệu năng sau**.

~~~java
import java.util.stream.IntStream;

int[] prefix = IntStream.range(0, 100)
        .parallel()
        .takeWhile(n -> n < 10)
        .toArray();

// Với nguồn range có thứ tự: [0,1,2,3,4,5,6,7,8,9].
~~~

Để giữ đúng tiền tố trong Stream có thứ tự, runtime có thể phải phối hợp các phần công việc trước và sau điểm cắt. Điều này khiến `takeWhile`/`dropWhile` trên ordered parallel stream **đắt hơn** pipeline tuần tự trong nhiều tình huống.

Đừng suy rằng:

- Chuyển `stream()` thành `parallelStream()` luôn nhanh hơn.
- `takeWhile` luôn chỉ gọi predicate đúng một lần cho mỗi phần tử quan sát được trong mọi cách thực thi.
- Thứ tự **chạy** predicate hoặc mapper luôn trùng encounter order.
- `dropWhile` giúp bỏ qua toàn bộ công việc trước mốc trên nguồn không cho truy cập ngẫu nhiên; nhiều nguồn vẫn phải được duyệt để xác định điểm cắt.

Nếu cần giới hạn chính xác “100 phần tử đầu”, dùng `limit(100)` trên nguồn có thứ tự. Nếu cần “mọi phần tử thỏa”, dùng `filter`. Nếu cần đoạn đầu trước một mốc trên nguồn đã sắp xếp, `takeWhile` phù hợp.

## 12. Phân biệt thao tác theo số lượng với thao tác theo điều kiện

| Nhu cầu | Phương thức | Phạm vi tác động |
| --- | --- | --- |
| Chỉ giữ giá trị khác null từ một giá trị | `Stream.ofNullable` | 0 hoặc 1 phần tử |
| Sinh từ seed đến khi điều kiện không còn đúng | `iterate(seed, hasNext, next)` | Nguồn có điều kiện dừng |
| Giữ mọi phần tử thỏa predicate bất kể vị trí | `filter(predicate)` | Toàn bộ dữ liệu được duyệt |
| Lấy liên tiếp từ đầu khi predicate còn đúng | `takeWhile(predicate)` | Tiền tố của Stream có thứ tự |
| Bỏ liên tiếp từ đầu khi predicate còn đúng | `dropWhile(predicate)` | Tiền tố bị bỏ, giữ hậu tố |
| Lấy tối đa N phần tử đầu | `limit(n)` | Đếm phần tử |
| Bỏ N phần tử đầu | `skip(n)` | Đếm phần tử |

Ví dụ `limit` và `takeWhile` đều có thể trả `[1,2,3]` trên một bộ dữ liệu, nhưng **không vì thế mà tương đương**. `limit(3)` không quan tâm giá trị; `takeWhile(n -> n < 4)` phụ thuộc điều kiện và thứ tự.

### Kết hợp các phương thức đúng mục đích

~~~java
import java.util.stream.IntStream;

// Sinh số từ 1 đến 100 (bao gồm 100), lấy khi còn nhỏ hơn 8,
// sau đó loại số chẵn:
int[] result = IntStream.iterate(1, n -> n <= 100, n -> n + 1)
        .takeWhile(n -> n < 8)
        .filter(n -> n % 2 != 0)
        .toArray();

// [1, 3, 5, 7]
~~~

Ở đây cả `iterate` và `takeWhile` đều có giới hạn, nhưng hai điều kiện phục vụ **hai mục tiêu khác nhau**: nguồn được phép sinh đến 100, còn pipeline cụ thể chỉ cần các số đầu trước 8. Trong mã thật, nếu chỉ cần `1..7`, có thể diễn đạt trực tiếp điều kiện dừng của `iterate` để tránh một tầng thao tác.

## 13. Nguồn vô hạn, lazy evaluation và quy tắc kết thúc

`Stream.iterate(seed, next)` hai tham số thường tạo nguồn không có điểm kết thúc được khai báo, trong khi `iterate(seed, hasNext, next)` cho phép kiểm tra điều kiện dừng.

~~~java
import java.util.stream.Stream;

long count = Stream.iterate(1, n -> n <= 5, n -> n + 1)
        .count();

System.out.println(count); // 5
~~~

Tuy nhiên, **có ba tham số không tự bảo đảm nguồn hữu hạn**: nếu `hasNext` luôn `true`, nguồn vẫn có thể không kết thúc.

~~~java
// Không dùng collect()/count() không giới hạn trên nguồn này:
Stream<Integer> endless = Stream.iterate(
        0,
        n -> true,
        n -> n + 1
);
~~~

Cũng không nên phụ thuộc vào bộ đếm mutable bên ngoài để “ép” predicate kết thúc. Một predicate stateful hoặc can thiệp nguồn có thể phá hợp đồng của các thao tác Stream, đặc biệt dưới thực thi song song.

### Tràn số và điều kiện dừng

Nếu sinh `int` gần `Integer.MAX_VALUE` rồi luôn cộng `1`, giá trị có thể tràn về số âm. Predicate kiểu `n <= end` có thể bắt đầu đúng trở lại và làm vòng sinh chạy ngoài dự tính.

Với một khoảng số nguyên thông thường, ưu tiên `IntStream.range`/`rangeClosed` khi phù hợp. Với dãy tính tiếp từ phần tử trước, hãy xác định miền số, điều kiện dừng và phép chuyển trạng thái không gây tràn hoặc dùng kiểu số đủ lớn.

### Tính lazy không có nghĩa cứ có takeWhile là đọc tệp an toàn

Các thao tác `ofNullable`, `iterate`, `takeWhile` và `dropWhile` tham gia vào pipeline Stream, nhưng chúng không giải quyết vấn đề **đóng tài nguyên**. Với nguồn `Files.lines(path)`, ngay cả khi `takeWhile` hoặc `findFirst` giúp dừng sớm, nguồn I/O vẫn cần `try-with-resources`.

## 14. Ví dụ tích hợp hoàn chỉnh, biên dịch với Java 9

Chương trình dưới đây sử dụng **chỉ các API có sẵn từ Java 9 trở xuống**, nên có thể biên dịch với `javac --release 9` trên JDK hiện đại. Chúng ta có danh sách sự kiện **đã sắp theo ngày tăng dần**; trace ID có thể null.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Java9StreamAdditionsDemo {

    static final class Event {
        final LocalDate date;
        final String service;
        final String traceId;

        Event(LocalDate date, String service, String traceId) {
            this.date = date;
            this.service = service;
            this.traceId = traceId;
        }
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(LocalDate.of(2026, 11, 15), "auth", "T-01"),
                new Event(LocalDate.of(2026, 11, 16), "search", null),
                new Event(LocalDate.of(2026, 11, 17), "auth", "T-03"),
                new Event(LocalDate.of(2026, 11, 19), "billing", null)
        );

        // ofNullable: một Event không có traceId sinh 0 phần tử.
        List<String> traces = events.stream()
                .flatMap(e -> Stream.ofNullable(e.traceId))
                .collect(Collectors.toList());

        // iterate 3 tham số: 15, 16, 17, 18/11 (không có 19/11).
        List<LocalDate> days = Stream.iterate(
                        LocalDate.of(2026, 11, 15),
                        day -> day.isBefore(
                                LocalDate.of(2026, 11, 19)),
                        day -> day.plusDays(1))
                .collect(Collectors.toList());

        LocalDate cutoff = LocalDate.of(2026, 11, 17);

        // takeWhile: chỉ giữ các sự kiện trước 17/11.
        List<String> before = events.stream()
                .takeWhile(e -> e.date.isBefore(cutoff))
                .map(e -> e.service)
                .collect(Collectors.toList());

        // dropWhile: bỏ phần trước 17/11, giữ phần còn lại.
        List<String> fromCutoff = events.stream()
                .dropWhile(e -> e.date.isBefore(cutoff))
                .map(e -> e.service)
                .collect(Collectors.toList());

        System.out.println("traces=" + traces);
        System.out.println("days=" + days);
        System.out.println("before=" + before);
        System.out.println("fromCutoff=" + fromCutoff);
    }
}
~~~

Kết quả:

~~~text
traces=[T-01, T-03]
days=[2026-11-15, 2026-11-16, 2026-11-17, 2026-11-18]
before=[auth, search]
fromCutoff=[auth, billing]
~~~

Lệnh thử nghiệm trên máy có JDK hỗ trợ tùy chọn `--release`:

~~~bash
javac --release 9 Java9StreamAdditionsDemo.java
java Java9StreamAdditionsDemo
~~~

**Tại sao ví dụ dùng nhiều Stream khác nhau?** Mỗi lời gọi `events.stream()` tạo một Stream mới từ `List` có thể duyệt lại. Nếu dùng lại một đối tượng Stream đã gọi terminal operation, chương trình sẽ không hợp lệ.

**Tại sao không dùng `Stream.toList()`?** Vì phương thức đó chỉ có từ Java 16; nó sẽ làm ví dụ **không còn là mã nguồn biên dịch được cho Java 9**.

## 15. Ứng dụng với tệp lớn: điều kiện về thứ tự và vòng đời I/O

Giả sử một tệp log có các dòng theo thứ tự thời gian tăng dần, mỗi dòng bắt đầu bằng một timestamp chuẩn. Chúng ta muốn lấy đoạn trước mốc theo nghiệp vụ.

Sơ đồ:

~~~text
Files.lines(...) -> parseLine -> takeWhile(event < cutoff) -> collect
       |                                        |
    I/O cần đóng                         cần sorted input
~~~

Cần bảo đảm cả hai điều kiện:

1. **Thứ tự:** tệp thực sự có thời gian tăng dần; nếu không, `takeWhile` bỏ lỡ các sự kiện cũ nằm sau một sự kiện mới.
2. **Vòng đời:** `Files.lines` phải được đóng dù pipeline chỉ đọc tiền tố.

Một phiên bản minh họa trên các chuỗi đã được xác nhận thứ tự:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readBeforeMarker(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
                .takeWhile(line -> !line.equals("--END-SECTION--"))
                .collect(Collectors.toList());
    }
}
~~~

Đây là ví dụ lấy dòng **trước một marker**, không phải parser timestamp: `takeWhile` giữ đúng tiền tố trước dòng `--END-SECTION--`, và **không** lấy marker. Nếu marker xuất hiện đầu tiên, kết quả rỗng. Nếu không có marker, toàn bộ dòng được thu vào List.

Đối với tệp cực lớn, ngay cả khi đóng nguồn đúng, `collect(toList())` vẫn có thể tốn nhiều bộ nhớ nếu đoạn tiền tố dài. Có thể thay terminal bằng phép tổng hợp như `count` hoặc `reduce` khi chỉ cần thống kê.

Nếu yêu cầu là **bỏ header đầu tệp** bằng `dropWhile`, cũng phải đặt toàn bộ pipeline bên trong `try-with-resources`. Không trả Stream lazy ra khỏi một khối `try` đã đóng nguồn.

## 16. Chuyển đổi codebase: Java 8 và Java 9

Khi dự án vẫn phải chạy trên Java 8, **không được gọi trực tiếp** các API chỉ xuất hiện ở Java 9. Những mẫu chuyển đổi phổ biến:

### 16.1. ofNullable trong Java 8

Java 9:

~~~java
Stream<String> result = Stream.ofNullable(maybeValue);
~~~

Java 8:

~~~java
Stream<String> result = maybeValue == null
        ? Stream.empty()
        : Stream.of(maybeValue);
~~~

Với pipeline `flatMap`:

~~~java
.flatMap(user -> user.email() == null
        ? Stream.<String>empty()
        : Stream.of(user.email()))
~~~

Dạng `map(User::email).filter(Objects::nonNull)` cũng có từ Java 8 và có thể rõ hơn nếu chỉ cần loại phần tử null.

### 16.2. iterate hữu hạn trong Java 8

Java 9:

~~~java
IntStream.iterate(1, n -> n <= 5, n -> n + 1)
~~~

Với dãy nguyên đơn giản, Java 8 có thể dùng:

~~~java
IntStream.rangeClosed(1, 5)
~~~

Hoặc với dãy tăng đều và số lượng phần tử đã biết:

~~~java
IntStream.iterate(1, n -> n + 1).limit(5)
~~~

Tuy nhiên, `limit(5)` chỉ biết **số lượng cần lấy**, không thay thế một điều kiện tùy ý như “lấy cho tới khi trạng thái đã kết thúc” trong mọi bài toán. Với nguồn có điều kiện dừng phức tạp trên Java 8, có thể cần một `Iterator`/`Spliterator` tùy chỉnh hoặc một vòng lặp rõ ràng.

### 16.3. takeWhile/dropWhile trên Java 8

Java 8 **không có** hai phương thức này. Chỉ thay bằng `filter` trong trường hợp nghiệp vụ thật sự là “lấy mọi phần tử thỏa predicate”, không phải “lấy/bỏ tiền tố”.

Ví dụ:

~~~text
Nguồn: [2, 4, 7, 8]

takeWhile(even) -> [2, 4]
filter(even)    -> [2, 4, 8]

dropWhile(even) -> [7, 8]
filter(odd)     -> [7]
~~~

Để bảo toàn chính xác semantics của tiền tố trên Java 8, sử dụng iterator có trạng thái, vòng lặp tuần tự hoặc triển khai Spliterator chuyên biệt; hãy kiểm thử đường đi gặp phần tử không thỏa đầu tiên và các phần tử phía sau.

### 16.4. Kiểm tra toolchain, không chỉ phiên bản java trên máy

Nếu code phải chạy trên Java 8 nhưng người phát triển đang dùng JDK mới hơn, chỉ dùng JDK mới **không có nghĩa** API Java 9 được phép sử dụng. Cần cấu hình đúng mức tương thích cho build.

Trên JDK hiện đại:

~~~bash
javac --release 8 MyJava8Source.java
javac --release 9 Java9StreamAdditionsDemo.java
~~~

`--release` kiểm soát mức ngôn ngữ và API nền tảng có thể sử dụng khi biên dịch cho phiên bản đích. Ví dụ Java 9 ở phần 14 **không** biên dịch được với `--release 8` vì các API Java 9 chưa tồn tại ở bản đích.

Ngược lại, chỉ đặt mức cú pháp tương thích cũ mà vẫn cho phép link API từ JDK mới có thể dẫn đến lỗi khi chạy trên runtime cũ. Vì vậy, cần xét **cả compiler, API target và runtime triển khai**.

Không cần thay đổi toàn bộ module sang phiên bản mới chỉ để dùng một phương thức tiện ích, nếu dự án có ràng buộc chạy trên JDK cũ. Hãy cân nhắc giải pháp tương thích hoặc nâng chuẩn JDK theo kế hoạch.

## 17. Các lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: ofNullable` hoặc `takeWhile` | Biên dịch với API đích Java 8 | Dùng `--release 9` trở lên nếu được phép nâng JDK, hoặc viết mẫu Java 8 tương đương |
| `NoSuchMethodError` khi chạy trên runtime cũ | Mã gọi API không có trong runtime đang chạy | Đồng bộ compiler target và runtime triển khai |
| `ofNullable(null)` làm mất bản ghi cần kiểm toán | Dùng null như dữ liệu có thể bỏ, trong khi nghiệp vụ yêu cầu báo lỗi | Kiểm tra bắt buộc trước hoặc giữ trạng thái thiếu dữ liệu riêng |
| `iterate` thiếu phần tử cuối | Dùng `<` thay vì `<=` trong hasNext | Xác định khoảng đóng/nửa mở và kiểm thử mốc |
| `iterate` không kết thúc | Predicate luôn đúng hoặc biến đếm tràn rồi quay lại miền đúng | Bảo đảm điều kiện kết thúc hữu hạn và miền số an toàn |
| `takeWhile` bỏ mất giá trị thỏa nằm phía sau | Dùng tiền tố thay cho lọc toàn bộ nguồn | Dùng `filter` nếu dữ liệu không có tính chất thứ tự/đơn điệu cần thiết |
| `dropWhile` giữ lại phần tử sau không mong muốn | Chỉ bỏ tiền tố, không loại mọi phần tử thỏa predicate | Dùng `filter` nếu cần bỏ mọi phần tử như vậy |
| Kết quả tiền tố khác nhau trên unordered stream | Nguồn không có encounter order hoặc đã gọi `unordered()` | Chọn nguồn có thứ tự/`sorted` phù hợp hoặc đổi nghiệp vụ sang `filter` |
| Parallel pipeline chậm hơn | Chi phí phối hợp để xác định tiền tố của nguồn có thứ tự | Đo hiệu năng và cân nhắc giữ tuần tự |
| `IllegalStateException` khi dùng lại Stream | Đã có terminal operation trên cùng Stream | Tạo Stream mới từ nguồn có thể duyệt lại |
| Tệp chưa đóng khi lấy xong tiền tố | Terminal operation không tự đóng nguồn I/O | Bao `Files.lines` trong `try-with-resources` |
| Có dòng log cũ bị bỏ sót sau cutoff | Tệp thực ra không được sắp theo timestamp | Xác thực thứ tự, dùng `filter` hoặc xử lý sắp xếp theo yêu cầu |

## 18. Bài tập tự kiểm tra

### Bài 1 — ofNullable với null và chuỗi rỗng

~~~java
long a = Stream.ofNullable((String) null).count();
long b = Stream.ofNullable("").count();
~~~

**Đáp án:** `a = 0` và `b = 1`. `ofNullable` chỉ kiểm tra `null`, không kiểm tra chuỗi rỗng.

### Bài 2 — Ranh giới iterate

~~~java
int[] data = IntStream.iterate(2, n -> n < 7, n -> n + 2)
        .toArray();
~~~

**Đáp án:** `[2, 4, 6]`. `hasNext(8)` là false nên 8 không được phát. Nếu seed ban đầu không thỏa predicate, Stream rỗng.

### Bài 3 — takeWhile có lấy số 8 không?

~~~java
List<Integer> source = List.of(2, 4, 7, 8, 10);

List<Integer> result = source.stream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

**Đáp án:** `[2, 4]`, không có 8 và 10. `takeWhile` chỉ lấy tiền tố chẵn trước số 7, không giống `filter`.

### Bài 4 — dropWhile có loại số chẵn nằm cuối không?

~~~java
List<Integer> result = List.of(2, 4, 7, 8, 10).stream()
        .dropWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

**Đáp án:** `[7, 8, 10]`. Sau số 7, toàn bộ hậu tố được giữ, kể cả số chẵn.

### Bài 5 — Chọn thao tác theo yêu cầu

Một nguồn sự kiện **không sắp theo thời gian**, cần lấy **mọi sự kiện trước 01/12/2026**. Nên dùng `takeWhile` hay `filter`?

**Đáp án:** `filter(event -> event.time().isBefore(cutoff))` nếu yêu cầu lấy tất cả. `takeWhile` chỉ đúng khi muốn tiền tố hoặc nguồn được bảo đảm có thứ tự phù hợp và điều kiện không thể đúng trở lại sau lần sai đầu tiên.

### Bài 6 — Dùng parallel và unordered

Một `HashSet` chứa các số nguyên, gọi `parallelStream().takeWhile(n -> n < 5)`. Có đảm bảo kết quả gồm toàn bộ số nhỏ hơn 5 không?

**Đáp án:** Không. Stream không có encounter order được bảo đảm; `takeWhile` được phép lấy một tập con của những phần tử thỏa predicate. Dùng `filter(n -> n < 5)` nếu cần mọi số nhỏ hơn 5.

### Bài 7 — Chương trình có thực sự tương thích Java 9?

~~~java
List<Integer> values = IntStream.range(0, 10)
        .boxed()
        .toList();
~~~

**Đáp án:** Không phải mã nguồn chỉ dùng API Java 9; `Stream.toList()` xuất hiện ở Java 16. Trên Java 9, dùng `collect(Collectors.toList())`.

### Bài 8 — Đóng tệp khi dropWhile

~~~java
long count = Files.lines(path)
        .dropWhile(line -> line.startsWith("#"))
        .count();
~~~

**Đáp án:** Thiếu quản lý vòng đời nguồn. Dùng:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines
            .dropWhile(line -> line.startsWith("#"))
            .count();
}
~~~

`count()` không tự đóng Stream, dù đã duyệt hết các dòng.

## 19. Ghi nhớ

- **Java 9** bổ sung `Stream.ofNullable`, overload `iterate(seed, hasNext, next)` và các thao tác `takeWhile`/`dropWhile`.
- `ofNullable` sinh **0 hoặc 1 phần tử**; nó phù hợp để bỏ giá trị tùy chọn, **không phải** cách tự động hợp thức hóa dữ liệu thiếu bắt buộc.
- `iterate` ba tham số kiểm tra `hasNext` **trước khi phát phần tử**, vì vậy phải xác định đúng biên trên/dưới và tránh điều kiện không kết thúc.
- `takeWhile` **lấy tiền tố liên tiếp** thỏa điều kiện; `dropWhile` **bỏ tiền tố liên tiếp** thỏa điều kiện, giữ cả phần tử đầu không thỏa và mọi phần tử sau đó.
- `filter` áp dụng cho **mọi phần tử**; `limit`/`skip` đếm số lượng. Không thay thế lẫn nhau nếu khác yêu cầu nghiệp vụ.
- Với **unordered stream**, hai thao tác tiền tố không còn bảo đảm chọn đúng tiền tố như với `List` có thứ tự. `parallel()` không tự làm mất encounter order, nhưng có thể khiến việc duy trì tiền tố tốn chi phí.
- Các thao tác trung gian vẫn mang tính lazy; nguồn I/O vẫn cần `try-with-resources` kể cả khi pipeline dừng sớm.
- Muốn tương thích Java 9, tránh các API ra đời muộn hơn như `Stream.toList()` (Java 16); dùng `javac --release 9` và kiểm tra runtime theo mục tiêu triển khai.

**Ý chính:** Bốn API này giúp mô hình hóa rõ **sự vắng mặt của giá trị**, **điểm dừng của nguồn sinh dãy** và **ranh giới tiền tố của dữ liệu có thứ tự**. Sử dụng đúng hợp đồng của chúng — nhất là khác biệt với `filter` và ràng buộc encounter order — sẽ tạo pipeline khai báo dễ hiểu, có thể dự đoán kết quả và tương thích chính xác với phiên bản JDK mà dự án hỗ trợ.
