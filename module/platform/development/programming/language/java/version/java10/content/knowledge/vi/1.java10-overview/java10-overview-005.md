# Quan hệ giữa `copyOf`, collector và thiết kế dữ liệu chỉ đọc (Java 10+)

## 1. Vấn đề cần giải quyết

Giả sử một lớp nhận danh sách cấu hình rồi trả danh sách đó cho nơi khác. Nếu hai bên cùng giữ tham chiếu đến một `ArrayList` có thể sửa, bên ngoài có thể thêm/xóa phần tử và làm thay đổi trạng thái mà lớp không kiểm soát. Java cung cấp hai nhóm thao tác rất gần nhau về mục tiêu nhưng khác **điểm xuất phát**:

- **Đã có `Collection` hoặc `Map`:** dùng `List.copyOf(source)`, `Set.copyOf(source)` hoặc `Map.copyOf(source)` để lấy một tập hợp **không cho sửa cấu trúc**, được tách khỏi những thay đổi cấu trúc tiếp theo của nguồn.
- **Đang tạo kết quả bằng Stream:** dùng `Collectors.toUnmodifiableList()`, `Collectors.toUnmodifiableSet()` hoặc `Collectors.toUnmodifiableMap(...)` để **thu thập và chốt kết quả không cho sửa** ở cuối pipeline.

Các phương thức `copyOf` và bộ `toUnmodifiable...` được bổ sung trong **Java 10** và tiếp tục hữu ích trên Java hiện đại. `List.of`/`Set.of`/`Map.of` có từ Java 9 cho tập hợp biết sẵn phần tử; `Stream.toList()` có từ Java 16 là lựa chọn ngắn hơn khi cần danh sách không sửa được từ Stream. Chọn API theo dữ liệu đầu vào và hợp đồng của đầu ra, không chỉ theo tên phương thức.

## 2. Phân biệt “chỉ đọc”, “không sửa được” và “bất biến”

**Unmodifiable collection** nghĩa là không thể thêm, xóa hay thay thế phần tử thông qua chính đối tượng tập hợp đó; thao tác thay đổi sẽ ném `UnsupportedOperationException`. Điều này **không tự động** bảo đảm mọi dữ liệu được tham chiếu bên trong là bất biến.

**Unmodifiable view** là lớp vỏ chỉ đọc bao quanh một collection khác. Ví dụ `Collections.unmodifiableList(source)` chặn `view.add(...)`, nhưng nếu ai đó gọi `source.add(...)`, thay đổi thường **xuất hiện ngay trong view** vì hai bên vẫn dùng cùng dữ liệu nền.

**Unmodifiable snapshot** từ `List.copyOf(source)` giữ nội dung tại thời điểm sao chép: thêm/xóa phần tử trên `source` sau đó không thay đổi kết quả `copyOf`. Tuy nhiên đây chỉ là **sao chép nông**: phần tử bên trong vẫn là những tham chiếu cũ. Nếu phần tử là `StringBuilder` hoặc một bean có setter, việc sửa trạng thái của phần tử ấy vẫn nhìn thấy qua cả hai collection.

**Immutability của toàn bộ mô hình** đòi hỏi cả container lẫn những đối tượng mà nó phơi bày đều bất biến hoặc được sao chép/phòng vệ thích hợp. Một biến khai báo `final List<T>` chỉ ngăn gán lại biến, không tự làm danh sách hoặc phần tử trở thành bất biến.

## 3. `copyOf`: chốt một bản nhìn độc lập khỏi thay đổi cấu trúc nguồn

Ba phương thức Java 10:

```java
List<E> result = List.copyOf(collection);
Set<E> unique = Set.copyOf(collection);
Map<K, V> lookup = Map.copyOf(map);
```

Các quy tắc quan trọng:

1. Kết quả không cho phép sửa cấu trúc; `add`/`remove`/`put` trên kết quả không hợp lệ.
2. Nguồn và phần tử/khóa/giá trị không được `null`. `copyOf(null)` hoặc nguồn chứa `null` sẽ dẫn tới `NullPointerException`.
3. `List.copyOf` giữ nguyên thứ tự duyệt của collection nguồn **tại lúc tạo bản sao** và cho phép phần tử lặp lại; nếu nguồn là `Set` không có thứ tự duyệt được bảo đảm, danh sách cũng không tự tạo ra thứ tự xác định.
4. `Set.copyOf` chỉ giữ các phần tử duy nhất theo `equals`; nếu nguồn có phần tử trùng, một đại diện bất kỳ được giữ lại, **không ném lỗi vì trùng**. Thứ tự duyệt của `Set` trả về không được bảo đảm.
5. `Map.copyOf` bảo toàn các ánh xạ khóa–giá trị tại thời điểm tạo; nó không hứa giữ thứ tự duyệt của `LinkedHashMap` hay `TreeMap` nguồn.
6. Nếu đầu vào đã là một tập hợp không sửa được phù hợp, triển khai **có thể tái sử dụng cùng instance** thay vì cấp phát bản sao. Không dùng `==`, `System.identityHashCode` hoặc khóa đồng bộ để suy luận về kết quả; hãy so sánh nội dung và dựa trên hợp đồng API.

Ví dụ: `List.copyOf(mutableList)` thích hợp để nhận dữ liệu ở biên constructor, setter kiểu “thay toàn bộ danh sách”, snapshot cấu hình hoặc tạo dữ liệu trả về mà người gọi không được thay đổi. Nó bảo vệ **cấu trúc collection**, chưa bảo vệ các đối tượng mutable chứa bên trong.

## 4. Collector: tạo kết quả chỉ đọc ngay trong pipeline

`Stream.collect(...)` gom các phần tử đã lọc/biến đổi thành một tập hợp. Java 10 cung cấp:

```java
List<String> names = people.stream()
    .map(Person::name)
    .collect(Collectors.toUnmodifiableList());

Set<String> codes = people.stream()
    .map(Person::code)
    .collect(Collectors.toUnmodifiableSet());

Map<String, Person> byId = people.stream()
    .collect(Collectors.toUnmodifiableMap(Person::id, Function.identity()));
```

Đoạn trên minh họa ý tưởng với kiểu `Person` giả định; hãy thay bằng lớp thực tế của ứng dụng. Điểm chính là **pipeline tạo ra kết quả cuối đã không sửa được** mà không cần gọi `List.copyOf(...)` thêm ở cuối.

- `toUnmodifiableList()` giữ thứ tự xuất hiện (encounter order) của Stream khi có thứ tự ấy và giữ các giá trị trùng; nó từ chối phần tử `null`.
- `toUnmodifiableSet()` loại giá trị trùng; một đại diện bất kỳ được giữ và thứ tự duyệt của tập kết quả không được bảo đảm. Phần tử `null` bị từ chối.
- `toUnmodifiableMap(keyMapper, valueMapper)` tạo map chỉ đọc. Nếu các phần tử sinh ra **khóa trùng** theo `equals`, nó ném `IllegalStateException`; khóa/giá trị `null` đều bị từ chối.
- Khi khóa trùng là trường hợp nghiệp vụ hợp lệ, dùng overload thứ ba `toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` và định nghĩa quy tắc gộp rõ ràng. Hàm gộp phải phù hợp cả khi Stream xử lý song song; ví dụ cộng số lượng là phép gộp phù hợp.

Ví dụ đếm số lần xuất hiện của từ, cần xử lý khóa trùng:

```java
Map<String, Long> counts = Stream.of("java", "go", "java")
    .collect(Collectors.toUnmodifiableMap(
        Function.identity(),
        word -> 1L,
        Long::sum
    ));
// counts.get("java") == 2L
```

Nếu bỏ `Long::sum`, từ `"java"` lặp lại tạo hai khóa bằng nhau và pipeline thất bại. Ngược lại, `List.copyOf(existingList)` **không** có bước giải quyết khóa trùng vì nó không tạo Map từ một Stream.

## 5. So sánh những cách thường gặp

| Nhu cầu | Cách dùng | Đặc điểm cần nhớ |
| --- | --- | --- |
| Khai báo vài giá trị cố định | `List.of("a", "b")` | Không sửa được, không nhận `null`; có từ Java 9. |
| Nhận collection đã có và chốt dữ liệu | `List.copyOf(source)` | Snapshot cấu trúc, sao chép nông; có từ Java 10. |
| Biến đổi/lọc Stream thành danh sách | `stream.collect(Collectors.toUnmodifiableList())` | Kết quả không sửa được, từ chối `null`; có từ Java 10. |
| Stream thành danh sách trên Java 16+ | `stream.toList()` | Không sửa được, giữ encounter order nếu có; **không đồng nhất hoàn toàn** với collector Java 10 về ràng buộc `null`. |
| Phơi bày collection đang được cập nhật bởi chủ sở hữu | `Collections.unmodifiableList(source)` | Chỉ là view: thay đổi tại `source` vẫn có thể hiện ra; không tạo snapshot. |
| Cần giữ `null` trong một snapshot chỉ đọc | `Collections.unmodifiableList(new ArrayList<>(source))` | Sao chép trước, bọc view sau; khác với `List.copyOf` ở chính sách `null`. |
| Cần tiếp tục chỉnh sửa danh sách | `new ArrayList<>(source)` | Tạo bản sao mutable; không dùng `copyOf` nếu hợp đồng yêu cầu cập nhật. |

`Collectors.toList()`, `Collectors.toSet()` và `Collectors.toMap()` **không cam kết** tính mutable/unmodifiable trong đặc tả. Không dựa vào hiện trạng implementation để thiết kế API. Nếu muốn đích mutable cụ thể, hãy yêu cầu rõ: `Collectors.toCollection(ArrayList::new)` hoặc `Collectors.toCollection(LinkedHashSet::new)`. Nếu muốn đích unmodifiable, chọn API cam kết điều đó.

**Lưu ý về `Stream.toList()`:** nó được bổ sung từ Java 16; không sử dụng khi dự án vẫn biên dịch với `--release 10`. Phương thức này không có chính sách cấm `null` giống `Collectors.toUnmodifiableList()`, nên không thay thế máy móc hai API ở luồng dữ liệu có thể chứa `null`. Cả hai đều trả về danh sách không sửa được, nhưng không nên giả định kiểu implementation, identity hay khả năng sửa giống nhau ở mọi collector.

## 6. Ví dụ chạy đầy đủ trên Java 17+

Tạo tệp `ReadOnlyCollectionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ReadOnlyCollectionsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("java", "spring"));
        List<String> snapshot = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);

        source.add("gradle");
        System.out.println("source: " + source);
        System.out.println("snapshot: " + snapshot);
        System.out.println("view: " + view);

        List<String> uppercase = source.stream()
                .map(String::toUpperCase)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("uppercase: " + uppercase);

        List<String> fromStream = source.stream()
                .map(String::toUpperCase)
                .toList();
        System.out.println("Stream.toList: " + fromStream);

        Map<String, Long> frequencies = Stream.of("a", "bb", "a")
                .collect(Collectors.toUnmodifiableMap(
                        Function.identity(),
                        item -> 1L,
                        Long::sum));
        System.out.println("count(a): " + frequencies.get("a"));

        StringBuilder builder = new StringBuilder("initial");
        List<StringBuilder> shallow = List.copyOf(List.of(builder));
        builder.append("-changed");
        System.out.println("element after mutation: " + shallow.get(0));

        try {
            snapshot.add("blocked");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
```

Biên dịch và chạy (hai lệnh riêng):

```bash
javac ReadOnlyCollectionsDemo.java
java ReadOnlyCollectionsDemo
```

Kết quả chính xác:

```text
source: [java, spring, gradle]
snapshot: [java, spring]
view: [java, spring, gradle]
uppercase: [JAVA, SPRING, GRADLE]
Stream.toList: [JAVA, SPRING, GRADLE]
count(a): 2
element after mutation: initial-changed
snapshot is unmodifiable
```

Giải thích: `source.add("gradle")` xuất hiện trong `view` vì view chia sẻ dữ liệu nền, nhưng `snapshot` vẫn giữ hai phần tử ban đầu. Cả collector và `Stream.toList()` chốt danh sách từ ba phần tử hiện tại. `StringBuilder` vẫn thay đổi được dù nó đang nằm trong một `List.copyOf`, cho thấy snapshot chỉ là sao chép nông. Hàm gộp `Long::sum` bảo đảm từ `"a"` xuất hiện hai lần không gây lỗi khóa trùng.

Nếu thử `uppercase.add("X")`, `fromStream.add("X")` hoặc `frequencies.put("x", 1L)`, thao tác thay đổi tương ứng sẽ bị từ chối bằng `UnsupportedOperationException`. Không cần thử sửa collection để kiểm tra loại triển khai trong mã ứng dụng; hãy dùng hợp đồng API.

## 7. Thiết kế lớp có API chỉ đọc và phòng vệ dữ liệu

Ví dụ một DTO/class giữ danh sách chủ đề: **sao chép khi nhận đầu vào, rồi trả thẳng tham chiếu tới snapshot không sửa được**. Đoạn sau dùng API từ Java 10, không cần record:

```java
import java.util.Collection;
import java.util.List;

public final class CourseCatalog {
    private final List<String> topics;

    public CourseCatalog(Collection<String> topics) {
        this.topics = List.copyOf(topics);
    }

    public List<String> topics() {
        return topics;
    }
}
```

Khi người gọi sửa collection đã truyền vào constructor, `CourseCatalog` không bị thay đổi cấu trúc. Khi người gọi nhận `topics()`, họ cũng không thể `add`/`remove` phần tử qua danh sách đó. Vì `String` bất biến, ví dụ này còn tránh được rủi ro thay đổi trạng thái phần tử. Nếu thay `String` bằng `List<MutableUser>`, chỉ `List.copyOf` **chưa đủ**: vẫn cần thiết kế `MutableUser` thành giá trị bất biến hoặc chuyển từng phần tử thành bản sao phòng vệ thích hợp.

Với dữ liệu lồng nhau, hãy phòng vệ **ở từng lớp cần giữ bất biến**. Chẳng hạn trong Java 17+, record có thành phần `List<String>` có thể thực hiện:

```java
import java.util.List;
import java.util.Objects;

public record Lesson(String title, List<String> tags) {
    public Lesson {
        Objects.requireNonNull(title, "title");
        tags = List.copyOf(tags);
    }
}
```

Ở ví dụ này, `title` và phần tử `tags` là `String` bất biến; constructor bảo vệ danh sách `tags`. Nếu record chứa mảng hoặc object mutable, bản thân từ khóa `record` **không** tạo deep copy. Đây là một ví dụ Java 17+; nó không phải cú pháp có sẵn trong Java 10.

Một chiến lược hữu ích là: **biên soạn/thay đổi bằng collection mutable trong phạm vi nội bộ → chuẩn hóa/lọc dữ liệu → chốt bằng `copyOf` hoặc collector → công bố tham chiếu chỉ đọc**. Nếu nội dung cần sửa theo thời gian, hãy quản lý bản mutable bên trong và công bố các snapshot mới; không sửa trực tiếp snapshot đã công bố.

## 8. Lỗi phổ biến và cách quyết định

1. **Nhầm view với snapshot:** `Collections.unmodifiableList(source)` không ngăn `source` thay đổi; nếu cần tách biệt, `List.copyOf(source)` rõ ý định hơn.
2. **Nhầm unmodifiable với deep immutable:** đối tượng phần tử mutable vẫn sửa được; cân nhắc immutable value object, ánh xạ sang DTO bất biến, defensive copy ở biên.
3. **Bỏ qua `null`:** `List/Set/Map.copyOf` và collector `toUnmodifiable...` không nhận giá trị `null` tương ứng. Xác định chính sách dữ liệu sớm: loại bỏ, thay bằng giá trị rõ ràng, hoặc dùng biểu diễn có chủ đích. Đừng phụ thuộc vào exception như một cơ chế làm sạch dữ liệu.
4. **Đụng khóa trùng khi gom Map:** `toUnmodifiableMap(k, v)` ném `IllegalStateException`; nếu trùng có ý nghĩa thì truyền `mergeFunction` theo luật nghiệp vụ, hoặc xử lý duplicate trước.
5. **Dựa vào thứ tự Set/Map:** không dựa vào thứ tự hiển thị của `Set.copyOf`, `Map.copyOf` hoặc `toUnmodifiableSet/Map`. Nếu thứ tự là hợp đồng API, dùng `List` hoặc thiết kế representation bảo toàn thứ tự một cách tường minh.
6. **Giả định luôn tạo object mới:** `copyOf` có thể tái sử dụng instance unmodifiable; không dùng identity để kiểm thử tính snapshot.
7. **Copy lại liên tục trong vòng lặp:** mỗi lần cần bản snapshot mới có thể tốn chi phí theo số phần tử. Gom/thay đổi trên bản mutable cục bộ, sau đó chốt một lần ở biên công bố; đo hiệu năng nếu khối lượng lớn.
8. **Dùng `Stream.toList()` trong Java 10:** phương thức này xuất hiện sau Java 10. Khi biên dịch với Java 10, dùng `collect(Collectors.toUnmodifiableList())`.

Để chọn nhanh: **nguồn đã là collection → `copyOf`; nguồn là Stream → `toUnmodifiable...`; giá trị cố định → `of`; muốn view phản ánh thay đổi của nguồn → `Collections.unmodifiable...`; muốn chỉnh sửa tiếp → collection mutable.** Sau đó đánh giá riêng chính sách `null`, duplicate, thứ tự và tính bất biến của **phần tử**.

## 9. Tự kiểm tra hiểu bài

- Có `List<User>` mà mỗi `User` có setter. `List.copyOf(users)` đã bảo đảm API của lớp hoàn toàn bất biến chưa? **Chưa**: danh sách không sửa cấu trúc được nhưng trạng thái `User` vẫn có thể thay đổi.
- Từ một Stream chứa hai đối tượng có cùng id, cần `Map<Id, Count>` chỉ đọc. Dùng gì? **`Collectors.toUnmodifiableMap(idMapper, countMapper, mergeFunction)`**, sau khi quyết định cách gộp.
- Muốn người gọi không thể thay đổi kết quả và cũng không thấy thay đổi cấu trúc về sau ở danh sách đầu vào. Chọn `Collections.unmodifiableList(source)` hay `List.copyOf(source)`? **`List.copyOf(source)`**.
- `Set.copyOf(List.of("x", "x"))` có phải ném lỗi vì phần tử trùng? **Không**, tập kết quả chỉ chứa một `"x"`; `Set.of("x", "x")` lại ném `IllegalArgumentException`.

## Tài liệu API chính thức còn áp dụng

- [Oracle Java: Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html)
- [`List.copyOf`, hợp đồng unmodifiable list](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [`Collectors` và các phương thức `toUnmodifiable...`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [`Stream.toList()`, có từ Java 16](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#toList())
