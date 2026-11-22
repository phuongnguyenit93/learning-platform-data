# Triển khai tryAdvance và forEachRemaining

## 1. Spliterator đứng ở đâu trong Java Stream API?

Trong **Java Stream API**, người học thường bắt đầu từ `Collection.stream()`, sử dụng pipeline lazy với `filter`, `map`, `reduce` và `collect`. Với các nguồn dữ liệu tự định nghĩa, câu hỏi khó hơn là: **Stream lấy lần lượt từng phần tử từ đâu, và biết khi nào đã hết dữ liệu?**

Một giao diện trung tâm giải quyết việc duyệt nguồn là **`Spliterator<T>`** (*splitable iterator*). Nó vừa mô tả cách **tiến qua các phần tử**, vừa có khả năng **tách phần dữ liệu còn lại** để Stream có thể cân nhắc xử lý song song.

```text
Nguồn tùy chỉnh (mảng, vùng dữ liệu, tệp, bộ sinh...)
                       |
                       v
                 Spliterator<T>
                 /       |       \
         tryAdvance  forEachRemaining  trySplit
             |             |             |
        một phần tử    phần còn lại   chia phần việc
                 \       |       /
                       v
               StreamSupport.stream(...)
                       |
                 filter / map / ...
                       |
                 collect / count / ...
```

Chương **Spliterator và nguồn tự định nghĩa** tập trung vào hai phương thức duyệt:

- `tryAdvance`: thử lấy **một** phần tử tiếp theo rồi đưa nó cho một `Consumer`.
- `forEachRemaining`: đưa **tất cả các phần tử còn lại** cho cùng một `Consumer`.

Hai phương thức phải dùng chung **trạng thái tiến độ duyệt**. Nếu `tryAdvance` đã lấy phần tử đầu tiên thì `forEachRemaining` phải tiếp tục từ phần tử thứ hai, không lặp lại phần tử đầu và không bỏ sót phần tử.

**Mục tiêu bài học:** hiểu hợp đồng và giá trị trả về của `tryAdvance`, biết vì sao `forEachRemaining` có triển khai mặc định, tự viết Spliterator có con trỏ đúng, kết hợp với `trySplit`/`estimateSize`/`characteristics`, tạo Stream bằng `StreamSupport` và nhận diện lỗi thường gặp khi xử lý song song, dữ liệu mutable hoặc nguồn I/O.

Các API `Spliterator` và `StreamSupport` đã có từ **Java 8**. Những ví dụ độc lập bên dưới chạy được với **Java 17+**, chủ yếu để thống nhất với các ví dụ hiện đại trong module `JAVA_STREAM_API`.

## 2. Đọc hợp đồng của tryAdvance

Chữ ký trên `Spliterator<T>`:

```java
boolean tryAdvance(Consumer<? super T> action);
```

Nó thử lấy một phần tử tiếp theo **nếu còn**, gọi `action.accept(element)`, sau đó báo kết quả:

| Giá trị trả về | Ý nghĩa | Có gọi `action` không? |
| --- | --- | --- |
| `true` | Đã xử lý được một phần tử | Có, đúng một lần trong một lời gọi thành công |
| `false` | Không còn phần tử nào | Không |

Khi đã hết nguồn, các lần gọi `tryAdvance` tiếp theo cũng phải báo `false`; không được tự động quay lại phần tử đầu hoặc phát thêm phần tử tưởng tượng.

Ví dụ dùng Spliterator sẵn có của một `List`:

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> cursor =
        List.of("A", "B", "C").spliterator();

boolean first = cursor.tryAdvance(System.out::println);  // In A
boolean second = cursor.tryAdvance(System.out::println); // In B
boolean third = cursor.tryAdvance(System.out::println);  // In C
boolean fourth = cursor.tryAdvance(System.out::println); // Không in

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(third);  // true
System.out.println(fourth); // false
```

**`tryAdvance` không trả về phần tử** mà trả về `boolean`. Phần tử được chuyển đến `Consumer` do caller cung cấp. Nếu cần đưa phần tử vào List, có thể dùng `list::add` làm action; trong pipeline Stream thông thường, framework sẽ cung cấp consumer tương ứng.

### Action không được là null

Hợp đồng API yêu cầu `action` khác `null`. Một triển khai tự viết nên kiểm tra ngay:

```java
Objects.requireNonNull(action, "action");
```

Nếu action bằng `null`, ném `NullPointerException` kể cả khi nguồn đã hết. Tránh code chỉ kiểm tra action sau khi đã xác định hết dữ liệu vì có thể làm sai hợp đồng.

### Không được dựa vào tác dụng phụ để kiểm soát nguồn

`Consumer` có thể in, ghi dữ liệu hoặc thay đổi biến của caller. Tuy nhiên, trong pipeline Stream, các hành động có tác dụng phụ có thể khiến ứng dụng khó dự đoán; không nên dùng log trong `tryAdvance`/mapper như một phần của kết quả nghiệp vụ. Lỗi của `action.accept(...)` sẽ truyền ra caller, và hợp đồng Spliterator **không bảo đảm trạng thái cụ thể sau khi action ném ngoại lệ**.

## 3. forEachRemaining: duyệt phần chưa được tiêu thụ

Chữ ký:

```java
void forEachRemaining(Consumer<? super T> action);
```

`forEachRemaining` không trả về số lượng hay danh sách. Nó gọi action cho **từng phần tử chưa được xử lý** theo thứ tự duyệt thích hợp và kết thúc khi nguồn hết.

```java
Spliterator<Integer> numbers =
        List.of(10, 20, 30, 40).spliterator();

numbers.tryAdvance(n -> System.out.println("Lần đầu: " + n));
// Lần đầu: 10

numbers.forEachRemaining(n -> System.out.println("Còn lại: " + n));
// Còn lại: 20
// Còn lại: 30
// Còn lại: 40

System.out.println(numbers.tryAdvance(System.out::println));
// false
```

Nếu gọi `forEachRemaining` ngay từ đầu, nó duyệt toàn bộ nguồn. Nếu gọi sau ba lần `tryAdvance` thành công, nó chỉ xử lý phần còn lại kể từ phần tử thứ tư. Nếu nguồn đã hết, `forEachRemaining` không gọi action lần nào.

Điều kiện `action` khác `null` cũng áp dụng cho `forEachRemaining`. Tương tự `tryAdvance`, nếu action ném ngoại lệ, không được tự suy đoán rằng Spliterator vẫn ở một trạng thái có thể khôi phục và tiếp tục chính xác.

### forEachRemaining có sẵn triển khai mặc định

Trong `Spliterator`, `forEachRemaining` là một **default method** có logic tương đương:

Logic của default implementation có thể diễn đạt đơn giản bằng:

```java
default void forEachRemaining(Consumer<? super T> action) {
    Objects.requireNonNull(action, "action");
    while (tryAdvance(action)) {
        // tryAdvance đã chuyển một phần tử cho action.
    }
}
```

Đoạn trên minh họa logic **bên trong interface**, không phải phương thức phải chép vào lớp triển khai. Vì `forEachRemaining` đã có default implementation, một lớp triển khai `Spliterator` có thể chỉ cần viết `tryAdvance` cùng các phương thức bắt buộc khác.

**Vì sao vẫn override?** Khi nguồn có cách duyệt liên tục hiệu quả hơn (ví dụ mảng hoặc bộ đệm với con trỏ), có thể override `forEachRemaining` để giảm chi phí lặp qua nhiều lời gọi `tryAdvance`. Lúc đó phải bảo đảm cả hai cách duyệt **cùng cập nhật con trỏ**, không đọc lại từ đầu.

## 4. Bắt đầu với một Spliterator tuần tự tối giản

Giả sử ta quản lý một mảng chuỗi nội bộ. Một Spliterator đầu tiên có thể **không hỗ trợ tách**; `trySplit()` trả `null`. Đây là lựa chọn hợp lệ nếu nguồn nhỏ, tuần tự hoặc khó tách:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

final class SimpleArraySpliterator implements Spliterator<String> {
    private final String[] data;
    private int cursor;

    SimpleArraySpliterator(String[] source) {
        this.data = Objects.requireNonNull(source, "source").clone();
    }

    @Override
    public boolean tryAdvance(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");

        if (cursor >= data.length) {
            return false;
        }

        action.accept(data[cursor++]);
        return true;
    }

    @Override
    public Spliterator<String> trySplit() {
        return null; // Không hỗ trợ chia phần còn lại.
    }

    @Override
    public long estimateSize() {
        return data.length - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
    }
}
```

Đây là một class minh họa độc lập có thể đặt cùng file với lớp chạy ví dụ (không được khai báo hai lớp `public` trong cùng một file Java). Những điểm cần thấy:

1. `data` chứa bản sao của mảng nguồn để tránh bị code gọi sửa cấu trúc mảng phía ngoài trong lúc duyệt.
2. `cursor` đánh dấu **chỉ số phần tử kế tiếp**; phần đã qua là khoảng `[0, cursor)`.
3. Nếu `cursor >= data.length`, `tryAdvance` trả `false` và không gọi action.
4. Sau một lượt thành công, con trỏ tăng lên đúng một.
5. `estimateSize()` đếm **số phần tử còn lại**, không phải số phần tử ban đầu.
6. `trySplit() == null` có nghĩa là không thể chia tiếp. Việc có `SUBSIZED` vẫn nhất quán ở đây vì Spliterator hiện tại luôn biết kích thước chính xác và không tạo Spliterator con.

`ORDERED` tuyên bố nguồn có encounter order theo chỉ số mảng; `SIZED` tuyên bố `estimateSize` chính xác; `SUBSIZED` yêu cầu các phần tách có kích thước chính xác; `IMMUTABLE` được dùng vì mảng nguồn đã được sao chép riêng và không bị thay đổi trong quá trình duyệt. Không khai báo `NONNULL` vì các phần tử của mảng `String[]` **có thể chứa null** nếu caller truyền vào.

### Thử kết hợp hai phương thức duyệt

```java
SimpleArraySpliterator spliterator =
        new SimpleArraySpliterator(new String[] {"A", "B", "C"});

spliterator.tryAdvance(System.out::println); // A
System.out.println(spliterator.estimateSize()); // 2

spliterator.forEachRemaining(System.out::println); // B, rồi C
System.out.println(spliterator.estimateSize()); // 0
System.out.println(spliterator.tryAdvance(System.out::println)); // false
```

Ví dụ này dùng **default `forEachRemaining`** của interface. Dù không override, nó vẫn tiếp tục từ đúng vị trí vì gọi lặp `tryAdvance` đã cập nhật con trỏ.

## 5. Override forEachRemaining mà không phá trạng thái

Nếu muốn duyệt hết phần tử còn lại bằng vòng lặp trực tiếp, thêm phương thức sau vào class:

```java
@Override
public void forEachRemaining(Consumer<? super String> action) {
    Objects.requireNonNull(action, "action");

    while (cursor < data.length) {
        action.accept(data[cursor++]);
    }
}
```

Đoạn này là một **phương thức thành viên** của `SimpleArraySpliterator` ở mục trước. Vì `cursor` là cùng trường với `tryAdvance` nên hai phương thức có thể gọi xen kẽ:

```text
data = [A, B, C, D], cursor = 0

tryAdvance()          -> A          cursor = 1
tryAdvance()          -> B          cursor = 2
forEachRemaining()    -> C, D       cursor = 4
tryAdvance()          -> false      cursor = 4
forEachRemaining()    -> không phát gì
```

Một số lỗi nguy hiểm cần tránh:

```java
// SAI: bắt đầu lại từ 0 thay vì cursor, gây lặp A/B.
for (int i = 0; i < data.length; i++) {
    action.accept(data[i]);
}

// SAI: tăng cursor sau cả vòng lặp thay vì theo phần tử,
// có thể phát sai hoặc không kết thúc đúng.
```

Trong ví dụ chính, `action.accept(data[cursor++])` tăng cursor trước khi lời gọi action hoàn tất. Nếu action ném ngoại lệ, trạng thái có thể đã thay đổi; điều này nằm trong giới hạn hợp đồng Spliterator, vốn không cam kết khả năng tiếp tục sau lỗi của action.

Không nhất thiết override `forEachRemaining` với mọi Spliterator. Trước tiên hãy có `tryAdvance` **đúng**, sau đó tối ưu khi đo được nhu cầu. Logic duyệt tối ưu phải được kiểm tra với các trường hợp: nguồn rỗng, phần còn lại rỗng, chỉ còn một phần tử, đã gọi `tryAdvance` trước đó và action ném lỗi.

## 6. Spliterator khác Iterator như thế nào?

`Iterator<T>` tập trung vào `hasNext()` và `next()`. `Spliterator<T>` gộp kiểm tra và xử lý phần tử trong một lời gọi `tryAdvance(action)`, cung cấp thông tin về kích thước và đặc tính, đồng thời cho phép tách phần còn lại:

| Khía cạnh | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Lấy phần tử | `hasNext()` và `next()` | `tryAdvance(action)` |
| Duyệt hết phần còn lại | `forEachRemaining(action)` | `forEachRemaining(action)` |
| Chia nguồn thành phần việc | Không có giao thức `trySplit` | `trySplit()` |
| Ước lượng số phần tử còn lại | Không có API chung | `estimateSize()` |
| Mô tả thứ tự/kích thước/tính chất | Không có bit đặc tính chuẩn như Spliterator | `characteristics()`, `hasCharacteristics(...)` |
| Phục vụ StreamSupport | Có thể bọc qua helper | Là nguồn trực tiếp để tạo Stream |

Đừng xây dựng Spliterator riêng nếu đã có API phù hợp. Với `Collection`, dùng `collection.spliterator()`. Với nguồn chỉ có `Iterator`, `Spliterators.spliteratorUnknownSize(iterator, characteristics)` là một lựa chọn có sẵn.

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

Iterator<String> iterator = List.of("A", "B", "C").iterator();
Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

long count = StreamSupport.stream(source, false).count();
System.out.println(count); // 3
```

Helper trên tạo Spliterator khi chưa biết trước chính xác kích thước; không tự gắn `SIZED` hoặc `SUBSIZED` chỉ vì dữ liệu ví dụ ngắn. Việc viết Spliterator tùy chỉnh đáng cân nhắc khi phải kiểm soát cách phân chia nguồn, trạng thái duyệt hoặc characteristics đặc biệt.

## 7. Kết nối Spliterator với StreamSupport

Hai cách phổ biến:

```java
Stream<T> StreamSupport.stream(
        Spliterator<T> spliterator,
        boolean parallel
);

IntStream StreamSupport.intStream(
        Spliterator.OfInt spliterator,
        boolean parallel
);
```

Đây là chữ ký minh họa; `StreamSupport` còn có overload nhận `Supplier` để trì hoãn việc lấy Spliterator đến lúc terminal operation bắt đầu.

Tạo Stream đối tượng từ Spliterator tự viết:

```java
import java.util.Arrays;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Spliterator<String> source =
        new SimpleArraySpliterator(new String[] {" An ", "Bình", " Chi "});

List<String> names = StreamSupport.stream(source, false)
        .map(String::strip)
        .filter(name -> !name.isBlank())
        .toList();

System.out.println(names); // [An, Bình, Chi]
```

Tham số `false` nghĩa là tạo **Stream tuần tự**; `true` nghĩa là tạo Stream có chế độ xử lý **song song**. Truyền `true` không bảo đảm chạy nhanh hơn hoặc bắt buộc nguồn phải được chia.

**Không tái sử dụng Spliterator sau khi đã tiêu thụ nguồn.** Tương tự Stream, đối tượng Spliterator có con trỏ và một chiều tiến. Nếu đã bị duyệt hết, tạo Stream mới từ **chính Spliterator đó** sẽ không mang lại các phần tử ban đầu. Muốn xử lý lại, tạo Spliterator mới từ nguồn.

## 8. Implement trySplit: mỗi phần xử lý một khoảng không giao nhau

`tryAdvance` và `forEachRemaining` giải quyết việc tiến qua phần dữ liệu hiện tại; `trySplit` giúp **chia phạm vi chưa duyệt** thành hai Spliterator khi nguồn phù hợp.

Với một dải chỉ số `[origin, fence)`, triển khai tốt thường:

1. Xác định điểm giữa `mid` chỉ từ phần **chưa duyệt**.
2. Trả một Spliterator mới quản lý nửa đầu `[origin, mid)`.
3. Cập nhật Spliterator hiện tại để quản lý nửa sau `[mid, fence)`.
4. Không làm trùng, mất hoặc đảo không cần thiết các phần tử khi ghép theo encounter order.

```text
Trước khi tách (cursor = 0, fence = 8):
[0 1 2 3 4 5 6 7]

trySplit()
   |
   +-- returned split: [0 1 2 3]   (prefix)
   |
   +-- current:        [4 5 6 7]   (suffix)

Mỗi Spliterator tự duy trì cursor/fence của mình.
```

Ví dụ `trySplit` cho một Spliterator đã có các trường `data`, `cursor` và `fence`:

```java
@Override
public Spliterator<String> trySplit() {
    int low = cursor;
    int mid = low + (fence - low) / 2;

    if (mid == low) {
        return null; // Còn 0 hoặc 1 phần tử, không tách thêm.
    }

    cursor = mid; // Spliterator hiện tại giữ [mid, fence).
    return new RangeStringSpliterator(data, low, mid);
}
```

Đoạn này thuộc mô hình **`RangeStringSpliterator`** đầy đủ ở mục 12, không phải có thể dán nguyên xi vào `SimpleArraySpliterator` (vì class đơn giản không có trường `fence` và constructor phạm vi).

**Lưu ý:** không bắt buộc mọi Spliterator phải tách được. Với một nguồn I/O tuần tự hoặc dữ liệu phát sinh từng bước mà không biết cách chia đúng, trả `null` thường đơn giản và an toàn hơn việc giả lập `trySplit` sai.

## 9. estimateSize và characteristics phải nói đúng sự thật

Hai phương thức quan trọng khác:

```java
long estimateSize();
int characteristics();
```

`estimateSize` trả về **ước lượng số phần tử còn lại**. Nếu không thể biết kích thước, nguồn có thể báo `Long.MAX_VALUE`; nếu gắn đặc tính `SIZED`, giá trị đó phải là số phần tử còn lại **chính xác** theo hợp đồng.

`characteristics` trả về các bit đặc tính bằng cách OR các hằng số:

| Đặc tính | Ý nghĩa thường gặp | Cần lưu ý |
| --- | --- | --- |
| `ORDERED` | Có encounter order xác định | `trySplit` phải giữ tiền tố đúng khi chia nguồn có thứ tự. |
| `SIZED` | Biết chính xác số phần tử còn lại | `estimateSize()` phải đúng, không được trả số tùy ý. |
| `SUBSIZED` | Mọi phần tách đều `SIZED` và `SUBSIZED` | Chỉ dùng khi giữ đúng hợp đồng cho các split con. |
| `IMMUTABLE` | Nguồn không thể bị sửa cấu trúc trong lúc duyệt | Không được gắn nếu nguồn có thể bị thay đổi ngoài ý muốn. |
| `CONCURRENT` | Nguồn hỗ trợ sửa đồng thời theo hợp đồng của nó | Không đồng nghĩa Spliterator có con trỏ thread-safe. |
| `NONNULL` | Không phát phần tử `null` | Không gắn với nguồn có khả năng chứa null. |
| `DISTINCT` | Không có hai phần tử trùng theo `equals` | Không tự suy ra chỉ vì nguồn là một mảng. |
| `SORTED` | Phần tử theo thứ tự sắp xếp được tuyên bố | Phải tuân thủ quy tắc comparator/`getComparator()`. |

Ví dụ với mảng `String[]` được sao chép riêng, truy cập theo chỉ số, không cho phép nguồn đổi:

```java
@Override
public int characteristics() {
    return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
}

@Override
public long estimateSize() {
    return fence - cursor;
}
```

Hai phương thức trên nằm trong `RangeStringSpliterator` ở mục 12. Không gắn `NONNULL` nếu chưa bảo đảm mọi phần tử đều khác null, và không gắn `SORTED` nếu mảng chưa được sắp theo một comparator phù hợp.

**Khai báo sai đặc tính có thể khiến Stream đưa ra tối ưu không phù hợp.** Ví dụ, khi một nguồn thực ra còn phần tử không đếm được nhưng lại tuyên bố `SIZED` với estimate sai, một số terminal operation như `count` có thể dựa vào thông tin kích thước mà không cần duyệt các phần tử như mong đợi. Do đó, đặc tính là một phần **hợp đồng nguồn**, không phải nhãn trang trí để tăng tốc.

## 10. Quan hệ giữa tryAdvance, forEachRemaining và trySplit

Một Spliterator tuân thủ hợp đồng phải bảo đảm phần tử không bị lặp hoặc mất khi caller sử dụng nhiều cách duyệt:

```text
Phạm vi ban đầu: [A, B, C, D, E, F]

tryAdvance()  -> A
remaining     -> [B, C, D, E, F]

trySplit()    -> returned prefix [B, C]
                 current suffix  [D, E, F]

returned.forEachRemaining() -> B, C
current.tryAdvance()        -> D
current.forEachRemaining()  -> E, F

Tất cả phần tử đầu vào xuất hiện đúng một lần:
A, B, C, D, E, F
```

Việc tách chỉ được phép tác động tới **phần chưa duyệt** của Spliterator đang được gọi. Phần đã tiêu thụ `[A]` không thể bất ngờ xuất hiện trong một split con.

Trong ví dụ có encounter order, khi `trySplit()` trả về một split con, nó phải đại diện cho **tiền tố** của phần chưa duyệt; Spliterator hiện tại giữ phần hậu tố còn lại. Điều này cho phép framework bảo toàn thứ tự logic của một nguồn ordered khi cần.

### Nguyên tắc an toàn cho trạng thái

- Mỗi instance của Spliterator có cursor riêng, không chia sẻ một biến `cursor` có thể bị hai split sửa đồng thời.
- Có thể chia sẻ vùng lưu dữ liệu **chỉ đọc** nếu mọi split chỉ đọc dữ liệu và duyệt các khoảng không giao nhau.
- `forEachRemaining` của một split không được duyệt vào khoảng của split khác.
- Không để một nguồn mutable thay đổi cấu trúc trong khi Splitter đang duyệt, trừ khi nguồn và characteristics có hợp đồng concurrent rõ ràng.
- Không dựa vào việc gọi `tryAdvance` hoặc `trySplit` từ nhiều thread **đồng thời trên chính một Spliterator instance**. Spliterator không mặc nhiên là cấu trúc thread-safe.

## 11. Vì sao Stream có thể dùng forEachRemaining?

Stream framework có thể lấy phần tử từ Spliterator bằng `tryAdvance`, hoặc dùng `forEachRemaining` khi xử lý tuần tự phần còn lại của một phần việc. Nó **không cam kết** số lần gọi mỗi phương thức cụ thể cho từng terminal operation.

Ví dụ sau minh họa cách **caller trực tiếp** sử dụng hai phương thức:

```java
Spliterator<String> s =
        List.of("alpha", "beta", "gamma").spliterator();

List<String> processed = new ArrayList<>();

boolean gotOne = s.tryAdvance(processed::add);
s.forEachRemaining(processed::add);

System.out.println(gotOne);    // true
System.out.println(processed); // [alpha, beta, gamma]
```

Trong pipeline Stream thực tế, framework có quyền lựa chọn chiến lược duyệt và tối ưu theo đặc tính nguồn. Vì vậy **không dùng biến đếm trong `tryAdvance`** để suy ra số phần tử đã qua `map` hoặc số phần tử terminal operation chắc chắn đã xử lý.

Một pipeline có `limit` hoặc `findFirst` có thể dừng sớm mà không yêu cầu duyệt toàn bộ nguồn. Ngược lại, các thao tác như `sorted` có thể phải thu thập dữ liệu trung gian. Khi thiết kế nguồn tùy chỉnh, hãy tập trung vào hợp đồng duyệt đúng trước khi tìm cách tối ưu.

## 12. Ví dụ đầy đủ: RangeStringSpliterator có cả bốn thao tác

Đoạn chương trình Java 17+ dưới đây là một triển khai độc lập cho mảng chuỗi **được sao chép**, có `tryAdvance`, `forEachRemaining`, `trySplit`, `estimateSize` và `characteristics`. Nó giữ encounter order theo chỉ số và có thể chia mảng thành các khoảng không giao nhau.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class CustomSpliteratorDemo {
    static final class RangeStringSpliterator implements Spliterator<String> {
        private final String[] data;
        private int cursor;
        private final int fence;

        RangeStringSpliterator(String[] source) {
            this(Objects.requireNonNull(source, "source").clone(),
                    0, source.length);
        }

        private RangeStringSpliterator(
                String[] data, int origin, int fence) {
            this.data = data;
            this.cursor = origin;
            this.fence = fence;
        }

        @Override
        public boolean tryAdvance(Consumer<? super String> action) {
            Objects.requireNonNull(action, "action");

            if (cursor >= fence) {
                return false;
            }
            action.accept(data[cursor++]);
            return true;
        }

        @Override
        public void forEachRemaining(Consumer<? super String> action) {
            Objects.requireNonNull(action, "action");

            while (cursor < fence) {
                action.accept(data[cursor++]);
            }
        }

        @Override
        public Spliterator<String> trySplit() {
            int low = cursor;
            int mid = low + (fence - low) / 2;
            if (mid == low) {
                return null;
            }

            cursor = mid;
            return new RangeStringSpliterator(data, low, mid);
        }

        @Override
        public long estimateSize() {
            return fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
        }
    }

    public static void main(String[] args) {
        String[] source = {"  An ", " Bình ", " Chi ", "Dũng"};

        // 1. Trực tiếp thử duyệt một phần tử rồi phần còn lại.
        Spliterator<String> cursor =
                new RangeStringSpliterator(source);
        cursor.tryAdvance(name -> System.out.println("Đầu: " + name));
        cursor.forEachRemaining(name -> System.out.println("Sau: " + name));
        System.out.println(cursor.estimateSize()); // 0

        // 2. Dùng một Spliterator mới để tạo Stream tuần tự.
        List<String> normalized = StreamSupport.stream(
                        new RangeStringSpliterator(source), false)
                .map(String::strip)
                .filter(name -> !name.isEmpty())
                .toList();
        System.out.println(normalized); // [An, Bình, Chi, Dũng]

        // 3. Chạy ở chế độ song song trên một nguồn tách được.
        List<String> parallel = StreamSupport.stream(
                        new RangeStringSpliterator(source), true)
                .map(String::strip)
                .toList();
        System.out.println(parallel); // [An, Bình, Chi, Dũng]

        // 4. Nguồn ban đầu có thể đổi nhưng snapshot mảng đã giữ riêng.
        Spliterator<String> snapshot =
                new RangeStringSpliterator(source);
        source[0] = "Changed";
        System.out.println(StreamSupport.stream(snapshot, false)
                .map(String::strip).findFirst().orElseThrow()); // An
    }
}
```

**Giải thích chính:**

1. Constructor public ở phạm vi package (không có `public`) **sao chép mảng một lần**. Các split con chia sẻ cùng mảng đã sao chép, chỉ khác cursor/fence, nên không cần tạo bản sao mảng ở mỗi lần tách.
2. `tryAdvance` xử lý tối đa một phần tử và trả `true` chỉ khi đã chuyển phần tử cho action.
3. `forEachRemaining` dùng **cùng cursor** nên không lặp lại phần đã duyệt.
4. `trySplit` trả một tiền tố của phần chưa duyệt, cập nhật instance hiện tại giữ hậu tố.
5. `estimateSize` luôn bằng `fence - cursor` cho từng split; mọi split biết kích thước chính xác.
6. `characteristics` tuyên bố các thuộc tính thật của nguồn. Không gắn `NONNULL` vì có thể có giá trị `null` bên trong mảng `String[]`.
7. Khi sử dụng `StreamSupport.stream(..., true)`, framework có thể tách và chạy các phần dữ liệu song song, nhưng kết quả `toList` vẫn giữ encounter order cho nguồn `ORDERED`.

**Giới hạn:** Đây là nguồn chứa toàn bộ mảng trong bộ nhớ; thao tác clone ban đầu có chi phí `O(n)`. Với mảng rất lớn hoặc dữ liệu phát sinh theo thời gian, cần thiết kế nguồn và vòng đời tài nguyên khác, không đơn giản copy mọi thứ. Ví dụ cũng không thay thế cơ chế validate chuỗi nếu phần tử có thể là `null` rồi pipeline gọi `String::strip`.

## 13. Primitive Spliterator: tránh boxing khi duyệt số

Nếu nguồn tùy chỉnh chỉ chứa số, các giao diện `Spliterator.OfInt`, `Spliterator.OfLong` và `Spliterator.OfDouble` cung cấp thao tác duyệt nguyên thủy và kết nối với `IntStream`, `LongStream`, `DoubleStream`.

```java
boolean tryAdvance(IntConsumer action);
void forEachRemaining(IntConsumer action);
```

Ví dụ `Spliterator.OfInt` cho dãy từ `start` (bao gồm) đến `endExclusive` (không bao gồm):

```java
import java.util.Objects;
import java.util.Comparator;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

final class IntRangeSpliterator implements Spliterator.OfInt {
    private int cursor;
    private final int fence;

    IntRangeSpliterator(int start, int endExclusive) {
        if (start > endExclusive) {
            throw new IllegalArgumentException("start > endExclusive");
        }
        this.cursor = start;
        this.fence = endExclusive;
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action, "action");
        if (cursor >= fence) return false;
        action.accept(cursor++);
        return true;
    }

    @Override
    public void forEachRemaining(IntConsumer action) {
        Objects.requireNonNull(action, "action");
        while (cursor < fence) action.accept(cursor++);
    }

    @Override
    public Spliterator.OfInt trySplit() {
        int low = cursor;
        int mid = low + (int) (((long) fence - low) / 2);
        if (mid == low) return null;
        cursor = mid;
        return new IntRangeSpliterator(low, mid);
    }

    @Override
    public long estimateSize() {
        return (long) fence - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE
                | NONNULL | DISTINCT | SORTED;
    }

    @Override
    public Comparator<? super Integer> getComparator() {
        return null; // SORTED theo thứ tự tự nhiên.
    }
}

long total = StreamSupport.intStream(
        new IntRangeSpliterator(1, 5), false).asLongStream().sum();
System.out.println(total); // 10 (1+2+3+4)
```

Nguồn này có các số tăng liên tục, không lặp và có thứ tự tự nhiên, nên các bit `DISTINCT` và `SORTED` được khai báo có căn cứ. Khi tuyên bố `SORTED`, lớp phải thực hiện đúng `getComparator()`: trả `null` nếu dùng thứ tự tự nhiên. Nếu không override, triển khai mặc định của `Spliterator.getComparator()` ném `IllegalStateException`, trái với đặc tính đã tuyên bố. Thao tác trên kiểu `int` không yêu cầu boxing thành `Integer` cho từng phần tử.

**Quan trọng:** ví dụ này không nên được dùng thay cho `IntStream.range(start, endExclusive)` khi chỉ cần dải số đơn giản; thư viện đã cung cấp nguồn chuẩn. Mục đích là minh họa cách triển khai các phương thức với `IntConsumer` và đặc tính hợp lệ của một primitive Spliterator.

## 14. Những lỗi thường gặp khi tự viết Spliterator

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `tryAdvance` báo `true` mãi mãi | Không tăng con trỏ hoặc không kiểm tra điều kiện kết thúc | Cập nhật cursor đúng một lần mỗi phần tử và trả `false` khi cạn nguồn |
| `tryAdvance` trả `false` nhưng vẫn gọi action | Sai hợp đồng hết nguồn | Kiểm tra cạn trước khi gọi `action.accept` |
| `forEachRemaining` lặp phần tử đã qua | Bắt đầu duyệt lại từ đầu thay vì con trỏ hiện tại | Chia sẻ cùng trạng thái tiến độ với `tryAdvance` |
| Mất phần tử khi xen kẽ hai phương thức | `forEachRemaining` có cursor riêng không đồng bộ | Dùng cùng cursor/fence, không tạo vòng duyệt độc lập |
| Gọi `trySplit` làm trùng hoặc thiếu phần tử | Hai split quản lý các phạm vi chồng nhau hoặc bỏ sót | Tách phần **chưa duyệt** thành các khoảng không giao nhau |
| Stream song song không phân chia | `trySplit()` luôn trả `null` | Chỉ triển khai tách khi nguồn hỗ trợ đúng và lợi ích phù hợp |
| `count()` trả số không đúng | Gắn `SIZED` nhưng `estimateSize()` sai | Đếm đúng phần tử còn lại hoặc bỏ `SIZED` |
| `NullPointerException` khi action null không nhất quán | Chỉ validate action nếu còn dữ liệu | Gọi `Objects.requireNonNull(action)` ngay đầu phương thức |
| `String::strip` ném `NullPointerException` | Mảng có phần tử null nhưng pipeline không xử lý | Lọc `null` hoặc validate nguồn trước biến đổi |
| Dữ liệu sai khi nguồn bị sửa | Spliterator duyệt nguồn mutable mà không đồng bộ/snapshot | Sao chép, khóa, hoặc dùng nguồn concurrent với hợp đồng phù hợp |
| Dữ liệu sai khi nhiều thread gọi cùng cursor | Cho phép hai thread thao tác cùng một instance Spliterator | Mỗi split giữ state riêng, không chia sẻ cursor mutable |
| `CONCURRENT`/`IMMUTABLE` bị khai báo tùy tiện | Hiểu nhầm characteristics là cờ tăng tốc | Chỉ gắn đặc tính có bảo đảm đúng từ nguồn |
| Dùng `StreamSupport.stream` hai lần với cùng cursor | Spliterator đã bị tiêu thụ | Tạo Spliterator mới khi cần duyệt lại |

## 15. Bài tập thực hành

Cho dữ liệu:

```java
String[] logs = {
        "OPEN",
        "FETCH",
        "PROCESS",
        "CLOSE",
        "ARCHIVE"
};
```

**Yêu cầu 1 — tryAdvance:** Viết `LogSpliterator` chứa mảng và con trỏ. Mỗi lời gọi `tryAdvance` thành công chỉ phát một dòng log, trả `true`; hết dữ liệu trả `false`.

**Yêu cầu 2 — forEachRemaining:** Override `forEachRemaining` để phát đúng những log còn lại. Gọi `tryAdvance` hai lần rồi `forEachRemaining`; dự kiến kết quả theo thứ tự là `OPEN, FETCH` trước, sau đó `PROCESS, CLOSE, ARCHIVE`.

**Yêu cầu 3 — kích thước:** Viết `estimateSize` để sau hai lần `tryAdvance` thành công báo `3`, sau `forEachRemaining` báo `0`.

**Yêu cầu 4 — characteristics:** Khai báo đặc tính đúng với mảng được sao chép riêng và duyệt theo chỉ số. Giải thích vì sao không mặc nhiên gắn `DISTINCT` hay `SORTED`.

**Yêu cầu 5 — mở rộng:** Nếu muốn xử lý song song, bổ sung `trySplit` tạo hai khoảng không giao nhau; kiểm chứng rằng gộp kết quả theo encounter order có đúng năm phần tử, không trùng hoặc thiếu.

### Lời giải tham khảo cho ba phương thức duyệt

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

final class LogSpliterator implements Spliterator<String> {
    private final String[] logs;
    private int cursor;

    LogSpliterator(String[] source) {
        logs = Objects.requireNonNull(source, "source").clone();
    }

    @Override
    public boolean tryAdvance(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");
        if (cursor == logs.length) return false;
        action.accept(logs[cursor++]);
        return true;
    }

    @Override
    public void forEachRemaining(Consumer<? super String> action) {
        Objects.requireNonNull(action, "action");
        while (cursor < logs.length) {
            action.accept(logs[cursor++]);
        }
    }

    @Override
    public Spliterator<String> trySplit() {
        return null; // Thử nghiệm tự bổ sung ở yêu cầu 5.
    }

    @Override
    public long estimateSize() {
        return logs.length - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
    }
}

LogSpliterator cursor = new LogSpliterator(logs);
cursor.tryAdvance(System.out::println); // OPEN
cursor.tryAdvance(System.out::println); // FETCH
System.out.println(cursor.estimateSize()); // 3
cursor.forEachRemaining(System.out::println);
// PROCESS, CLOSE, ARCHIVE
System.out.println(cursor.estimateSize()); // 0
```

Ở phần mở rộng, có thể tham khảo cách chia dải `[origin, fence)` ở mục 12. Đừng sửa trực tiếp mảng `logs` khi một Stream đang duyệt nó. Với dữ liệu có thể có phần tử trùng hoặc chưa được sắp xếp, `DISTINCT` và `SORTED` sẽ là những cam kết sai.

## 16. Checklist tự kiểm tra trước khi dùng nguồn tùy chỉnh

1. **Điểm dừng:** `tryAdvance` chắc chắn trả `false` khi đã cạn nguồn chưa?
2. **Một phần tử:** mỗi lần trả `true` có gọi action cho đúng một phần tử không?
3. **Con trỏ:** `forEachRemaining` có bắt đầu từ vị trí hiện tại và kết thúc ở vị trí cuối không?
4. **Null:** `action == null` có bị từ chối ngay bằng `NullPointerException` không?
5. **Tách nguồn:** `trySplit` có chỉ chia phần chưa duyệt thành những phạm vi không giao nhau không?
6. **Kích thước:** `estimateSize` có phản ánh số còn lại? Nếu gắn `SIZED`/`SUBSIZED`, có đúng sau mọi thao tác không?
7. **Đặc tính:** các cờ `ORDERED`/`IMMUTABLE`/`NONNULL`/`SORTED` có thật sự đúng với nguồn và từng split không?
8. **Tài nguyên:** nếu nguồn gắn với tệp/đường truyền/kết nối, đã có chính sách đóng tài nguyên bằng `onClose` hoặc `try-with-resources` thích hợp chưa?
9. **Song song:** mỗi split quản lý state riêng và dữ liệu nguồn đủ ổn định để duyệt chưa?
10. **Kiểm thử:** đã xét nguồn rỗng, nguồn một phần tử, xen kẽ hai phương thức, gọi sau khi cạn, tách sau khi đã tiến và action ném ngoại lệ chưa?

Với nguồn có vòng đời tài nguyên, chỉ trả `false` khi không còn phần tử không phải lúc nào cũng đồng nghĩa đã giải phóng tệp hoặc kết nối. Nếu tự tạo Stream từ một Spliterator dựa trên I/O, hãy thiết kế cơ chế đóng riêng và sử dụng `try-with-resources` ở nơi tiêu thụ.

## Ghi nhớ

`tryAdvance(action)` là thao tác duyệt **tối đa một phần tử**: trả `true` sau khi chuyển một phần tử cho action, trả `false` khi đã hết nguồn và không gọi action nữa. `forEachRemaining(action)` xử lý **toàn bộ phần chưa duyệt**, thường có thể dựa trên default implementation gọi lặp `tryAdvance`; chỉ override khi có lợi ích rõ ràng và phải dùng cùng trạng thái con trỏ.

Để dùng Spliterator làm nguồn cho Stream, ngoài hai phương thức duyệt còn cần khai báo đúng `trySplit`, `estimateSize` và `characteristics`. Mọi khoảng được tách phải không chồng nhau; các đặc tính như `SIZED`, `ORDERED` hay `IMMUTABLE` phải phản ánh hợp đồng thật của nguồn. Ưu tiên **tính đúng đắn của việc duyệt và không mất/lặp phần tử**, rồi mới tối ưu `forEachRemaining` hoặc xử lý song song bằng `StreamSupport`.
