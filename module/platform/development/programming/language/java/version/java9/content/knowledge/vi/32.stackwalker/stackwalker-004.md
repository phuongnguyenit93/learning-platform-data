# Phạm vi sống của Stream trong walk

`StackWalker.walk()` của Java 9 mở một `Stream<StackWalker.StackFrame>` để duyệt call stack của **luồng hiện tại**, rồi truyền stream đó cho một hàm `Function`. Stream chỉ hợp lệ trong lúc hàm này đang được thực thi. Khi `walk()` trả về, StackWalker đóng stream; nếu tiếp tục sử dụng stream đã đóng, chương trình sẽ nhận `IllegalStateException`.

Điểm cần nhớ là `Stream` của Java xử lý dữ liệu theo kiểu lazy. Các thao tác trung gian như `map()`, `filter()`, `skip()` và `limit()` chỉ mô tả pipeline; chúng chưa nhất thiết duyệt frame. Vì vậy, thao tác kết thúc như `collect()`, `findFirst()` hoặc `forEach()` phải chạy **bên trong callback của `walk()`**. Giá trị trả về của callback nên là kết quả đã được materialize, chẳng hạn `List<String>`, `List<StackFrame>`, `Optional<T>` hoặc một đối tượng tổng hợp.

## Mục tiêu

- Hiểu chữ ký và cách thực thi của `StackWalker.walk(Function)`.
- Biết chính xác khi nào stream được mở và đóng.
- Phân biệt thao tác trung gian lazy với thao tác kết thúc.
- Trả kết quả đã xử lý ra ngoài callback thay vì trả stream.
- Tạo snapshot frame để dùng sau khi `walk()` kết thúc.
- Tránh lưu stream, iterator hoặc spliterator để dùng ở thread khác.
- Xử lý short-circuit, lỗi trong callback và nhu cầu xử lý bất đồng bộ.

## 1. walk() nhận hàm xử lý stream

Chữ ký API:

~~~java
<T> T walk(Function<? super Stream<StackFrame>, ? extends T> function)
~~~

`walk()` tạo stream tuần tự của các frame thuộc thread đang gọi, sau đó áp dụng hàm được truyền vào. Kiểu `T` là kiểu kết quả mà hàm đó trả về. Vì vậy, `walk()` không trả trực tiếp một stream còn mở để caller tùy ý duyệt sau này.

Ví dụ lấy tên các frame:

~~~java
List<String> names = WALKER.walk(frames -> frames
    .limit(5)
    .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
    .collect(Collectors.toList())
);
~~~

Trong ví dụ này, `collect()` chạy trước khi callback kết thúc. `walk()` trả về một `List<String>` đã được tạo xong; list có thể được đọc sau khi `walk()` trả về.

## 2. Thời điểm stream bị đóng

Vòng đời của stream có thể mô tả như sau:

~~~text
StackWalker.walk(function)
        |
        v
Tạo Stream<StackFrame>
        |
        v
Gọi function(stream) trên thread hiện tại
        |
        +--> map/filter/skip/limit (xây dựng pipeline)
        |
        +--> collect/findFirst/forEach (tiêu thụ dữ liệu)
        |
        v
Function trả về kết quả T
        |
        v
StackWalker đóng stream
        |
        v
walk() trả về T cho caller
~~~

Stream được đóng khi `walk()` kết thúc, kể cả khi callback trả về một kết quả khác kiểu stream. Nếu callback trả chính stream ra ngoài, caller chỉ nhận được một stream đã đóng.

Việc đóng stream là một phần hợp đồng của `StackWalker`, không phụ thuộc vào việc caller có gọi `close()` hay không. Không cần bọc stream trong try-with-resources chỉ để đóng nó; StackWalker quản lý thời gian sống của stream.

## 3. Vì sao phải tiêu thụ stream trong callback?

Stream API có các thao tác trung gian và thao tác kết thúc.

| Nhóm | Ví dụ | Hành vi |
| --- | --- | --- |
| Trung gian | `map()`, `filter()`, `skip()`, `limit()`, `distinct()` | Trả về pipeline mới; thường chưa duyệt frame ngay |
| Kết thúc | `collect()`, `forEach()`, `count()`, `findFirst()`, `anyMatch()` | Bắt đầu duyệt và tạo kết quả hoặc tác dụng phụ |

Đoạn mã sau chỉ tạo pipeline rồi trả nó khỏi callback:

~~~java
Stream<String> names = WALKER.walk(frames ->
    frames.map(StackWalker.StackFrame::getClassName)
);
~~~

`map()` là thao tác lazy. Callback trả về khi chưa có terminal operation. Khi `walk()` trả về, stream frame đã bị đóng; biến `names` không thể được dùng để bắt đầu duyệt stack sau đó.

Cách đúng là đặt terminal operation bên trong callback:

~~~java
List<String> names = WALKER.walk(frames -> frames
    .map(StackWalker.StackFrame::getClassName)
    .collect(Collectors.toList())
);
~~~

Caller nhận một danh sách dữ liệu đã được thu thập, không nhận pipeline còn phụ thuộc vào stream của StackWalker.

## 4. Không trả Stream ra ngoài walk()

Ví dụ sai về phạm vi:

~~~java
private static Stream<StackWalker.StackFrame> frames() {
    return WALKER.walk(stream -> stream);
}

Stream<StackWalker.StackFrame> saved = frames();
saved.forEach(System.out::println); // IllegalStateException
~~~

Callback trả về đúng stream đầu vào. Tuy nhiên, StackWalker đóng stream trước khi `frames()` trả về cho caller. Khi caller gọi `forEach()`, stream đã đóng nên phát sinh `IllegalStateException`.

Không nên cố khắc phục bằng cách lưu stream vào field, `AtomicReference`, collection hoặc truyền stream vào một executor. Việc đổi nơi lưu giữ không kéo dài vòng đời của stream.

### 4.1. Iterator và Spliterator cũng không phải cách thoát khỏi giới hạn

Không lấy `iterator()` hoặc `spliterator()` trong callback rồi giữ chúng để duyệt sau. Các đối tượng này vẫn phụ thuộc vào nguồn dữ liệu của stream StackWalker và không biến stack walk thành một snapshot độc lập.

Nếu cần dùng kết quả sau callback, hãy thu thập các giá trị cần thiết thành một cấu trúc dữ liệu riêng trong callback.

## 5. Trả về dữ liệu đã materialize

`walk()` có thể trả về bất kỳ kiểu kết quả nào phù hợp với kiểu generic `T`. Một số dạng thường dùng:

| Kiểu kết quả | Trường hợp sử dụng |
| --- | --- |
| `List<String>` | Lưu tên class, method hoặc thông tin đã định dạng |
| `List<StackTraceElement>` | Giữ biểu diễn stack trace quen thuộc |
| `List<StackFrame>` | Snapshot danh sách frame theo mẫu API của StackWalker |
| `Optional<T>` | Tìm một frame đầu tiên thỏa điều kiện |
| `String` hoặc số | Tạo thông tin tổng hợp như caller, độ sâu hoặc mô tả |
| DTO riêng | Lưu các trường cần thiết cho log, telemetry hoặc xử lý tiếp |

### 5.1. Snapshot tên class và method

~~~java
List<String> frames = WALKER.walk(stream -> stream
    .limit(10)
    .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
    .collect(Collectors.toList())
);
~~~

Đây là lựa chọn gọn nếu mục tiêu là log hoặc hiển thị call chain. Chuỗi đã tách khỏi stream và có thể chuyển sang thread khác.

### 5.2. Snapshot StackTraceElement

Nếu cần file name, line number và biểu diễn stack trace, chuyển frame ngay trong callback:

~~~java
List<StackTraceElement> trace = WALKER.walk(stream -> stream
    .limit(10)
    .map(StackWalker.StackFrame::toStackTraceElement)
    .collect(Collectors.toList())
);
~~~

`StackTraceElement` là đối tượng dữ liệu thích hợp để lưu hoặc ghi log sau khi stack walk kết thúc.

### 5.3. Snapshot StackFrame

API của StackWalker cũng minh họa việc thu thập frame vào list:

~~~java
List<StackWalker.StackFrame> frames = WALKER.walk(stream -> stream
    .limit(10)
    .collect(Collectors.toList())
);
~~~

Điểm quan trọng là terminal operation `collect()` hoàn tất bên trong callback. Danh sách là kết quả trả về của `walk()`. Nếu ứng dụng chỉ cần một vài thuộc tính, snapshot thành `String`, `StackTraceElement` hoặc DTO riêng thường giúp giảm phụ thuộc vào API frame.

## 6. Short-circuit và giới hạn số frame

Không phải lúc nào cũng cần thu thập toàn bộ stack. Các thao tác short-circuit có thể dừng duyệt sớm:

~~~java
Optional<String> firstApplicationFrame = WALKER.walk(stream -> stream
    .filter(frame -> frame.getClassName().startsWith("com.example."))
    .map(StackWalker.StackFrame::getClassName)
    .findFirst()
);
~~~

`findFirst()` trả `Optional<String>` ngay trong callback. Khi kết quả đã tìm được và callback kết thúc, StackWalker đóng stream.

Ví dụ lấy tối đa năm frame:

~~~java
List<String> topFive = WALKER.walk(stream -> stream
    .limit(5)
    .map(StackWalker.StackFrame::getMethodName)
    .collect(Collectors.toList())
);
~~~

`limit(5)` là thao tác trung gian; `collect()` mới tiêu thụ pipeline. Cả hai phải nằm trong callback.

## 7. Xử lý bất đồng bộ: snapshot trước, gửi dữ liệu sau

StackWalker duyệt stack của thread gọi `walk()`. Stream được cấp cho callback cũng chỉ sống trong lời gọi đó; tài liệu API nêu rõ việc xử lý pipeline chỉ diễn ra trên thread hiện tại.

Do đó, không gửi stream sang thread khác:

~~~java
// Sai: tác vụ có thể chạy sau khi walk() đã đóng stream.
executor.submit(() -> WALKER.walk(stream -> {
    executor.submit(() -> stream.forEach(this::record));
    return null;
}));
~~~

Thay vào đó, hoàn tất stack walk và tạo snapshot trước, rồi chuyển snapshot sang executor:

~~~java
List<StackTraceElement> snapshot = WALKER.walk(stream -> stream
    .limit(20)
    .map(StackWalker.StackFrame::toStackTraceElement)
    .collect(Collectors.toList())
);

executor.submit(() -> record(snapshot));
~~~

Như vậy, công việc bất đồng bộ chỉ dùng dữ liệu đã được materialize; nó không phụ thuộc vào stream đã đóng hay stack của thread khác.

## 8. forEach() khi chỉ cần xử lý ngay

Nếu chỉ muốn thực hiện một hành động cho từng frame và không cần trả về kết quả, `StackWalker.forEach()` là cách viết ngắn hơn:

~~~java
WALKER.forEach(frame ->
    System.out.println(frame.getClassName() + "#" + frame.getMethodName())
);
~~~

`forEach(action)` tương đương về ý tưởng với `walk(stream -> { stream.forEach(action); return null; })`. Consumer được gọi trong quá trình stack walk; không có stream để caller giữ lại.

Nếu cần lọc, giới hạn, tìm kiếm hoặc trả kết quả, dùng `walk()`. Nếu chỉ cần xử lý trực tiếp từng frame, dùng `forEach()`.

## 9. Ngoại lệ và kết thúc callback

Callback có thể ném runtime exception khi xử lý frame. Khi callback không hoàn tất bình thường, ngoại lệ được truyền ra caller của `walk()`; không nên bắt rồi bỏ qua nếu ứng dụng cần biết việc lấy stack thất bại.

~~~java
try {
    List<String> frames = WALKER.walk(stream -> stream
        .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
        .collect(Collectors.toList())
    );
} catch (RuntimeException error) {
    logStackWalkFailure(error);
    throw error;
}
~~~

Đặt các bước xử lý có thể thất bại trong callback đồng nghĩa chúng chạy trong thời gian stack walk còn hiệu lực. Nếu công việc sau đó có thể chậm hoặc block, hãy snapshot trước rồi xử lý dữ liệu sau callback.

Không dùng callback để chờ tác vụ bất đồng bộ sẽ tiêu thụ stream. Pipeline phải được tiêu thụ đồng bộ trong callback; nếu callback chờ executor nhưng executor lại cần stream đã được đóng, thiết kế có thể tạo deadlock hoặc lỗi vòng đời.

## 10. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ này có hai đường xử lý:

- `captureFrames()` tiêu thụ stream bằng `collect()` bên trong callback và trả về `List<String>` để caller dùng sau.
- `returnStreamIncorrectly()` cố tình trả stream ra ngoài. `walk()` đóng stream trước khi caller nhận được; gọi terminal operation sau đó ném `IllegalStateException`.

**Tệp:** `StackWalkerStreamScopeDemo.java`

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StackWalkerStreamScopeDemo {
    private static final StackWalker WALKER = StackWalker.getInstance();

    public static void main(String[] args) {
        System.out.println("-- materialized snapshot --");
        captureFrames().forEach(System.out::println);

        Stream<StackWalker.StackFrame> returned = returnStreamIncorrectly();
        try {
            returned.count();
            throw new AssertionError("The walk stream should already be closed");
        } catch (IllegalStateException expected) {
            System.out.println("returned stream is closed");
        }
    }

    private static List<String> captureFrames() {
        return WALKER.walk(frames -> frames
            .limit(3)
            .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
            .collect(Collectors.toList())
        );
    }

    private static Stream<StackWalker.StackFrame> returnStreamIncorrectly() {
        return WALKER.walk(frames -> frames);
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 StackWalkerStreamScopeDemo.java
java StackWalkerStreamScopeDemo
~~~

Output:

~~~text
-- materialized snapshot --
StackWalkerStreamScopeDemo#captureFrames
StackWalkerStreamScopeDemo#main
returned stream is closed
~~~

Giải thích:

1. `captureFrames()` gọi `WALKER.walk()` và giới hạn tối đa ba frame.
2. `map()` chuyển frame thành chuỗi `class#method`.
3. `collect(Collectors.toList())` tiêu thụ stream trước khi callback trả về.
4. `walk()` đóng stream và trả `List<String>` cho `main()`.
5. `returnStreamIncorrectly()` trả chính stream đầu vào. StackWalker đóng stream khi `walk()` kết thúc.
6. `returned.count()` cố tái sử dụng stream đã đóng, vì vậy ném `IllegalStateException` và chương trình in thông báo xác nhận.

Ví dụ dùng `Collectors.toList()` để tương thích Java 9. Không dùng `Stream.toList()` trong bài cần biên dịch bằng Java 9 vì phương thức đó chỉ được bổ sung ở Java 16.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trả `Stream<StackFrame>` khỏi callback | StackWalker đóng stream khi `walk()` trả về | Dùng `collect()` trong callback và trả collection |
| Chỉ gọi `map()` rồi nghĩ frame đã được duyệt | `map()` là thao tác trung gian lazy | Thực hiện terminal operation trước khi callback kết thúc |
| Lưu stream vào field hoặc biến toàn cục | Lưu tham chiếu không kéo dài vòng đời stream | Lưu dữ liệu đã materialize |
| Chuyển stream sang executor | Tác vụ có thể chạy sau khi stream bị đóng; stack walk thuộc thread gọi | Snapshot trong callback rồi gửi snapshot sang executor |
| Lấy iterator rồi dùng sau callback | Iterator vẫn phụ thuộc stream nguồn | Thu thập dữ liệu thành list trong callback |
| Chạy nhiều terminal operation trên cùng stream | Stream chỉ được tiêu thụ một lần | Tạo một kết quả tổng hợp trong một lần duyệt hoặc snapshot rồi xử lý list |
| Thu thập mọi frame dù chỉ cần caller gần nhất | Duyệt thừa và tạo dữ liệu không cần thiết | Dùng `findFirst()`, `limit()` hoặc `skip()` phù hợp |
| Dùng `Stream.toList()` trong mã Java 9 | API chưa tồn tại trong Java 9 | Dùng `collect(Collectors.toList())` |
| Block lâu trong callback | Kéo dài thời gian giữ stack walk và làm chậm thread hiện tại | Snapshot nhanh, chuyển công việc nặng sang bước sau |

## 12. Quy tắc thực hành

1. Xem stream truyền vào `walk()` là tài nguyên có phạm vi trong callback.
2. Hoàn tất thao tác kết thúc như `collect()`, `findFirst()` hoặc `forEach()` trước khi callback trả về.
3. Trả về `List`, `Optional`, chuỗi, số hoặc DTO; không trả stream để dùng sau.
4. Không lưu stream, iterator hoặc spliterator vào field hoặc truyền sang executor.
5. Snapshot các thuộc tính cần dùng; chọn `String`, `StackTraceElement` hoặc DTO theo nhu cầu.
6. Dùng `limit()` và short-circuit operation khi chỉ cần một phần stack.
7. Dùng `forEach()` nếu chỉ cần xử lý frame ngay mà không cần stream pipeline hoặc giá trị trả về.
8. Giữ callback ngắn; thực hiện I/O hoặc công việc nặng sau khi đã materialize dữ liệu.
9. Nhớ rằng stack walk được thực hiện trên thread gọi và pipeline không được chuyển thành xử lý song song.
10. Dùng `Collectors.toList()` trong mã cần tương thích Java 9.

## 13. Tự kiểm tra

- Khi nào stream của `StackWalker.walk()` bị đóng? Khi phương thức `walk()` trả về.
- Dùng lại stream đã đóng gây lỗi gì? `IllegalStateException`.
- Vì sao chỉ gọi `map()` chưa đủ? Vì đây là thao tác trung gian lazy; cần terminal operation để tiêu thụ stream.
- `walk()` trả về kiểu gì? Kiểu `T` do hàm callback trả về.
- Có thể trả `List<String>` ra ngoài callback không? Có, nếu list được tạo bằng terminal operation bên trong callback.
- Có nên trả `Stream<StackFrame>` để xử lý sau không? Không, stream đã bị StackWalker đóng.
- Có thể chuyển stream sang executor khác không? Không; hãy snapshot dữ liệu trong callback rồi chuyển snapshot.
- `StackWalker.forEach()` phù hợp khi nào? Khi chỉ cần xử lý ngay từng frame và không cần giá trị trả về.
- Có thể chạy pipeline stream song song để duyệt stack không? Không; StackWalker thực hiện pipeline trên thread hiện tại.
- Java 9 dùng API nào để thu thập stream thành list? `collect(Collectors.toList())`.

## Tài liệu API

- [StackWalker — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/StackWalker.html)
- [StackWalker.StackFrame — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/StackWalker.StackFrame.html)

Điểm cốt lõi: **`walk()` sở hữu vòng đời của stream frame.** Tiêu thụ stream ngay trong callback và trả về dữ liệu đã materialize; sau khi `walk()` kết thúc, stream được đóng và không thể dùng lại.