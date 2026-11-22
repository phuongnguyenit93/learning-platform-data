# Tạo luồng có thể rỗng bằng Stream.ofNullable

`Stream.ofNullable(value)` là phương thức được bổ sung trong Java 9 để chuyển một giá trị có thể là `null` thành một Stream an toàn: nếu giá trị khác null, kết quả là luồng tuần tự chứa đúng một phần tử; nếu giá trị là null, kết quả là luồng rỗng. Nhờ đó, mã có thể đưa một giá trị tùy chọn vào pipeline Stream mà không cần tự viết nhánh `if (value == null)`.

Phương thức này đặc biệt hữu ích khi dữ liệu đầu vào có thể thiếu, khi cần nối một giá trị đơn với pipeline đang có, hoặc khi cần biến một container có thể null thành luồng các phần tử. Cần phân biệt rõ trường hợp container null với trường hợp container có chứa phần tử null.

## 1. Cú pháp và hợp đồng của ofNullable

Chữ ký API:

~~~java
static <T> Stream<T> ofNullable(T t)
~~~

Cách sử dụng:

~~~java
Stream<String> present = Stream.ofNullable("Java");
Stream<String> absent = Stream.ofNullable((String) null);
~~~

Kết quả:

- `present` chứa một phần tử là chuỗi `"Java"`.
- `absent` là một Stream rỗng, không chứa phần tử nào.
- Cả hai đều là Stream tuần tự và có thể tiếp tục kết hợp với các thao tác như `map`, `filter`, `flatMap` hoặc `forEach`.

Có thể hiểu tương đương với logic:

~~~java
value == null ? Stream.empty() : Stream.of(value)
~~~

Đây chỉ là cách diễn giải hành vi. Khi viết mã, dùng trực tiếp `Stream.ofNullable(value)` giúp thể hiện ý định rõ ràng hơn.

Nếu truyền trực tiếp literal null, nên cung cấp kiểu đích hoặc ép kiểu để mã dễ đọc và tránh vấn đề suy luận kiểu trong các biểu thức phức tạp:

~~~java
Stream<String> empty = Stream.ofNullable(null);
Stream<String> alsoEmpty = Stream.ofNullable((String) null);
~~~

## 2. Phân biệt ofNullable, of và empty

Ba cách tạo Stream này có hành vi khác nhau khi đầu vào là null:

| Cách tạo | Đầu vào | Kết quả |
|---|---|---|
| `Stream.ofNullable(value)` | Khác null | Stream có đúng một phần tử |
| `Stream.ofNullable(value)` | null | Stream rỗng |
| `Stream.of(value)` | Khác null | Stream có đúng một phần tử |
| `Stream.of((String) null)` | null được ép kiểu rõ ràng | Stream có một phần tử null |
| `Stream.empty()` | Không cần đầu vào | Stream rỗng |

Điểm quan trọng là `Stream.ofNullable(null)` biểu diễn “không có phần tử”, còn `Stream.of((String) null)` biểu diễn “có một phần tử mà giá trị của nó là null”.

Hai trạng thái này không giống nhau. Trong nhiều pipeline, phần tử null có thể gây lỗi ở thao tác phía sau. Ví dụ, `findFirst()` ném `NullPointerException` nếu phần tử được chọn là null, vì kết quả của nó được biểu diễn bằng Optional và Optional không chứa null.

~~~java
long emptyCount = Stream.ofNullable((String) null).count(); // 0
long nullCount = Stream.of((String) null).count();          // 1
~~~

Nếu ý nghĩa nghiệp vụ của null là “không có dữ liệu”, hãy dùng `ofNullable`. Nếu null là một giá trị cần được bảo toàn và xử lý riêng, hãy dùng một mô hình dữ liệu biểu diễn rõ trạng thái đó thay vì vô tình chuyển null thành luồng rỗng.

## 3. Đưa một giá trị nullable vào pipeline

Giả sử một phương thức trả về tên người dùng có thể null. Có thể chuyển kết quả thành Stream rồi xử lý bằng cùng một pipeline:

~~~java
String findDisplayName() {
    return "An";
}

Stream.ofNullable(findDisplayName())
    .map(String::trim)
    .filter(name -> !name.isEmpty())
    .map(String::toUpperCase)
    .forEach(System.out::println);
~~~

Nếu phương thức trả về null, Stream rỗng được tạo ra. Các thao tác trung gian không nhận phần tử nào và thao tác kết thúc không được gọi cho phần tử đó.

Cách viết này phù hợp khi phần xử lý tiếp theo vốn đã được tổ chức thành pipeline. Nếu chỉ cần một nhánh điều kiện đơn giản hoặc cần trả về một giá trị mặc định, một câu lệnh điều kiện hoặc `Optional` có thể dễ đọc hơn. Không cần ép mọi xử lý null thành Stream.

### Kết hợp nhiều nguồn nullable

Có thể nối nhiều giá trị tùy chọn thành một luồng:

~~~java
Stream<String> names = Stream.concat(
    Stream.ofNullable(primaryName),
    Stream.ofNullable(backupName)
);
~~~

Nếu một trong hai giá trị null, nguồn tương ứng đóng góp zero phần tử. Nếu cả hai khác null, kết quả có hai phần tử theo thứ tự primary rồi backup.

Có thể dùng `Stream.ofNullable` nhiều lần trong `Stream.concat`, hoặc dùng `Stream.ofNullable` kết hợp với `flatMap` khi nguồn dữ liệu đã là một Stream.

## 4. Xử lý container có thể null

Một collection có thể null khác với một collection không null nhưng chứa phần tử null. Để chuyển collection nullable thành luồng các phần tử:

~~~java
Collection<String> maybeNames = loadNames();

Stream<String> names = Stream.ofNullable(maybeNames)
    .flatMap(Collection::stream);
~~~

Nếu `maybeNames` là null, `Stream.ofNullable` tạo luồng rỗng; `Collection::stream` không được gọi. Nếu collection tồn tại, các phần tử của nó được đưa vào pipeline.

Tương tự với mảng:

~~~java
String[] maybeTags = loadTags();

Stream<String> tags = Stream.ofNullable(maybeTags)
    .flatMap(Arrays::stream);
~~~

Cần chú ý: `Stream.ofNullable(maybeTags)` tự nó tạo một Stream có một phần tử là cả mảng khi mảng khác null. Nó không tự tách mảng thành từng phần tử. `flatMap(Arrays::stream)` mới chuyển các phần tử trong mảng thành phần tử của luồng kết quả.

Nếu cần phân biệt rõ một container không tồn tại với container rỗng, hãy xử lý trạng thái đó ở tầng nghiệp vụ. Khi chuyển cả hai sang Stream, cả hai đều có thể dẫn tới luồng rỗng và thông tin về nguyên nhân không còn được giữ trong kết quả.

## 5. Loại bỏ phần tử null bên trong một luồng

`Stream.ofNullable(collection)` chỉ xử lý trường hợp chính collection là null. Nó không tự loại bỏ những phần tử null nằm bên trong collection.

Ví dụ:

~~~java
List<String> names = Arrays.asList("An", null, "Binh");

Stream<String> allElements = names.stream();
~~~

Luồng trên vẫn có phần tử null ở giữa. Nếu muốn bỏ qua các phần tử null, có thể dùng một trong hai cách:

~~~java
Stream<String> withoutNulls = names.stream()
    .filter(Objects::nonNull);
~~~

Hoặc:

~~~java
Stream<String> withoutNulls = names.stream()
    .flatMap(Stream::ofNullable);
~~~

Hai cách trên đều giữ lại các phần tử khác null theo thứ tự encounter order. Cách dùng `flatMap(Stream::ofNullable)` thể hiện trực tiếp việc biến mỗi giá trị nullable thành zero hoặc một phần tử trong luồng đầu ra.

Không nên nhầm thao tác này với việc xử lý một collection nullable. Nếu collection cũng có thể null và các phần tử bên trong cũng có thể null, có thể kết hợp hai bước:

~~~java
Stream<String> safeNames = Stream.ofNullable(maybeNames)
    .flatMap(Collection::stream)
    .flatMap(Stream::ofNullable);
~~~

## 6. Kết hợp với Optional.stream()

Java 9 cũng bổ sung `Optional.stream()`. Phương thức này chuyển Optional thành Stream:

- Optional có giá trị: Stream chứa một phần tử.
- Optional rỗng: Stream rỗng.

~~~java
Optional<String> selectedName = findName();

Stream<String> nameStream = selectedName.stream();
~~~

Với một giá trị nullable trực tiếp, `Stream.ofNullable(value)` thường ngắn gọn hơn. Với dữ liệu đã được mô hình hóa bằng Optional, dùng `optional.stream()` thể hiện đúng kiểu dữ liệu hiện có.

Một trường hợp hữu ích là làm phẳng danh sách Optional:

~~~java
List<Optional<String>> results = List.of(
    Optional.of("Java"),
    Optional.empty(),
    Optional.of("Stream")
);

List<String> values = results.stream()
    .flatMap(Optional::stream)
    .toList();
~~~

Kết quả là danh sách `[Java, Stream]`. Optional rỗng đóng góp zero phần tử.

Phân biệt `map` và `flatMap`:

- `map(Optional::stream)` tạo ra Stream chứa các Stream, tức cấu trúc lồng nhau.
- `flatMap(Optional::stream)` nối nội dung các Stream con thành một luồng duy nhất.

## 7. Tính lazy và vòng đời Stream

`Stream.ofNullable(value)` tạo đối tượng Stream ngay khi lời gọi phương thức được thực hiện. Các thao tác trung gian như `map`, `filter` và `flatMap` được thực thi lazy; chúng chỉ xử lý phần tử khi có thao tác kết thúc như `count`, `collect`, `toList` hoặc `forEach`.

Ví dụ:

~~~java
Stream.ofNullable("Java")
    .map(value -> {
        System.out.println("map: " + value);
        return value.toUpperCase();
    });

System.out.println("pipeline created");
~~~

Đoạn mã trên chỉ in `pipeline created`. Không có dòng `map: Java` vì chưa có thao tác kết thúc để tiêu thụ Stream.

Khi thêm `forEach(System.out::println)`, pipeline mới được thực thi. Mỗi Stream chỉ nên được tiêu thụ một lần; sau thao tác kết thúc, không sử dụng lại Stream đó cho một pipeline khác.

Ngoài ra, biểu thức truyền vào `ofNullable` vẫn được đánh giá trước khi phương thức được gọi. Nếu lời gọi tạo giá trị ném ngoại lệ, `ofNullable` không bắt hoặc chuyển ngoại lệ đó thành Stream rỗng:

~~~java
Stream.ofNullable(loadValue()); // loadValue() vẫn có thể ném ngoại lệ
~~~

`ofNullable` chỉ xử lý giá trị null mà nó nhận được, không xử lý ngoại lệ từ quá trình tạo giá trị hay từ các thao tác phía sau.

## 8. Ví dụ Java chạy được

Ví dụ sau minh họa giá trị nullable, sự khác nhau giữa Stream rỗng và phần tử null, container nullable, phần tử null trong collection và Optional.stream().

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class StreamOfNullableExamples {
    public static void main(String[] args) {
        singleValues();
        nullableContainer();
        nullElements();
        optionalValues();
    }

    private static void singleValues() {
        System.out.println("-- nullable value --");
        Stream.ofNullable("Java").forEach(System.out::println);
        System.out.println("null count="
            + Stream.ofNullable((String) null).count());
        System.out.println("explicit null element count="
            + Stream.of((String) null).count());
    }

    private static void nullableContainer() {
        System.out.println("-- nullable array --");
        String[] words = {"Java", "Stream"};
        String[] missing = null;

        Stream.ofNullable(words)
            .flatMap(Arrays::stream)
            .forEach(System.out::println);

        System.out.println("missing array count="
            + Stream.ofNullable(missing)
                .flatMap(Arrays::stream)
                .count());
    }

    private static void nullElements() {
        System.out.println("-- null elements --");
        List<String> words = Arrays.asList("A", null, "B");

        words.stream()
            .flatMap(Stream::ofNullable)
            .forEach(System.out::println);
    }

    private static void optionalValues() {
        System.out.println("-- optional stream --");
        Optional<String> present = Optional.of("Java");
        Optional<String> empty = Optional.empty();

        Stream.concat(present.stream(), empty.stream())
            .forEach(System.out::println);
    }
}
~~~

Lưu trong tệp `StreamOfNullableExamples.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all StreamOfNullableExamples.java
java StreamOfNullableExamples
~~~

Kết quả stdout chính xác:

~~~text
-- nullable value --
Java
null count=0
explicit null element count=1
-- nullable array --
Java
Stream
missing array count=0
-- null elements --
A
B
-- optional stream --
Java
~~~

Phân tích:

1. `Stream.ofNullable("Java")` tạo luồng một phần tử nên in ra Java.
2. `Stream.ofNullable((String) null)` tạo luồng rỗng, vì vậy count bằng 0.
3. `Stream.of((String) null)` tạo luồng có một phần tử null, vì vậy count bằng 1. Không nên gọi `findFirst()` trên luồng này nếu không muốn nhận NullPointerException.
4. Mảng `words` khác null được tách thành hai phần tử bằng `flatMap(Arrays::stream)`. Mảng `missing` null đóng góp zero phần tử.
5. `flatMap(Stream::ofNullable)` loại bỏ phần tử null ở giữa collection và giữ lại A, B.
6. Optional có giá trị tạo một phần tử; Optional rỗng tạo luồng rỗng.

## 9. Những lỗi thường gặp

- **Dùng `Stream.of(value)` cho một giá trị có thể null:** có thể tạo luồng chứa null. Dùng `Stream.ofNullable(value)` khi null có nghĩa là không có phần tử.
- **Nghĩ rằng `ofNullable(array)` tự tách mảng:** sai. Nó tạo luồng một phần tử là chính mảng; dùng `flatMap(Arrays::stream)` để lấy các phần tử bên trong.
- **Nghĩ rằng collection nullable đã được xử lý thì các phần tử null cũng biến mất:** sai. Cần lọc hoặc `flatMap(Stream::ofNullable)` thêm một bước.
- **Dùng `map` khi muốn nối nội dung các Stream con:** sẽ tạo cấu trúc Stream lồng nhau. Dùng `flatMap` để làm phẳng.
- **Cho rằng ofNullable bắt mọi NullPointerException:** sai. Nó chỉ xử lý đối số null; ngoại lệ từ biểu thức tạo đối số hoặc pipeline vẫn được truyền ra.
- **Dùng lại Stream sau terminal operation:** Stream đã được tiêu thụ; hãy tạo một Stream mới từ nguồn nếu cần xử lý lần nữa.
- **Coi luồng rỗng và luồng có một phần tử null là như nhau:** sai. Số phần tử, hành vi terminal operation và ý nghĩa dữ liệu khác nhau.

## 10. Khi nào nên dùng Stream.ofNullable?

Dùng `Stream.ofNullable` khi một giá trị đơn có thể null và bước xử lý tiếp theo đã phù hợp với Stream pipeline. Dùng `Stream.ofNullable(container).flatMap(...)` khi chính collection hoặc mảng có thể null. Dùng `flatMap(Stream::ofNullable)` khi muốn loại bỏ các phần tử null trong một luồng hiện có.

Nếu cần biểu diễn sự hiện diện hoặc vắng mặt của một giá trị trong API, `Optional<T>` có thể mô tả ý nghĩa đó rõ hơn. Nếu cần trả về nhiều phần tử, một collection hoặc Stream phù hợp hơn. Hãy chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ, rồi dùng `ofNullable` tại ranh giới nơi một giá trị nullable cần tham gia pipeline.

## 11. Tài liệu tham khảo chính thức

- [Stream — Java SE 25 API, ofNullable(T)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#ofNullable(T)): hợp đồng và hành vi của phương thức `Stream.ofNullable`.
- [Optional — Java SE 25 API, stream()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html#stream()): chuyển Optional thành Stream rỗng hoặc một phần tử.
- [Stream — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): các thao tác trung gian, thao tác kết thúc, đặc tính lazy và vòng đời Stream.
- [Dev.java — Stream API](https://dev.java/learn/api/streams/): hướng dẫn hiện hành về pipeline, intermediate operations và terminal operations.