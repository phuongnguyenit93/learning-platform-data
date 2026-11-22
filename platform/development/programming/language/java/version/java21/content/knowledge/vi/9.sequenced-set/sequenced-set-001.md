# SequencedSet và sự kết hợp giữa tính duy nhất với encounter order

Trong Java 21, `SequencedSet<E>` kết hợp hai đặc tính: mỗi phần tử chỉ xuất hiện một lần như mọi `Set`, đồng thời thứ tự duyệt (encounter order) được xác định rõ như một sequenced collection. Nhờ vậy, ứng dụng có thể vừa bảo đảm tính duy nhất, vừa thao tác trực tiếp với phần tử đầu và cuối của tập hợp.

`SequencedSet` được bổ sung trong Java 21 qua JEP 431 — Sequenced Collections. Đây là API đã hoàn thiện, sử dụng bình thường mà không cần bật Preview.

## 1. Vì sao cần SequencedSet?

`Set` bảo đảm không có hai phần tử trùng nhau theo quy tắc `equals()`, nhưng interface `Set` không cam kết một encounter order chung cho mọi implementation. Ví dụ, `HashSet` không bảo đảm thứ tự duyệt ổn định theo thứ tự thêm phần tử.

`LinkedHashSet` duy trì thứ tự chèn, nhưng trước Java 21, mã nguồn thường phải dựa vào kiểu implementation cụ thể hoặc tự chuyển collection sang cấu trúc khác để thao tác ở hai đầu. `SequencedSet` cung cấp một hợp đồng chung cho những tập hợp vừa duy nhất vừa có thứ tự.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

static SequencedSet<String> createTags() {
    SequencedSet<String> tags = new LinkedHashSet<>();
    tags.addLast("java");
    tags.addLast("backend");
    tags.addLast("cloud");
    return tags;
}
```

`LinkedHashSet` là implementation quen thuộc của `SequencedSet` và giữ encounter order theo thứ tự chèn. Khai báo biến bằng interface `SequencedSet` giúp mã gọi thể hiện rõ nhu cầu về thứ tự và các thao tác ở hai đầu.

## 2. Hai đặc tính cùng tồn tại: uniqueness và encounter order

`SequencedSet` kế thừa cả `Set<E>` và `SequencedCollection<E>`. Do đó:

- **Tính duy nhất:** một phần tử không thể xuất hiện nhiều lần trong set; việc xác định trùng lặp tuân theo hợp đồng của `Set`.
- **Encounter order:** khi duyệt set, các phần tử xuất hiện theo một thứ tự xác định do implementation quy định.
- **Thao tác hai đầu:** có thể đọc, thêm hoặc loại bỏ phần tử ở đầu và cuối khi implementation hỗ trợ thao tác tương ứng.
- **Duyệt ngược:** có thể lấy một view thể hiện cùng tập hợp theo encounter order ngược lại.

Encounter order không có nghĩa mọi implementation đều dùng thứ tự thêm vào. `LinkedHashSet` dùng thứ tự chèn; một `SortedSet` như `TreeSet` dùng thứ tự do comparator hoặc natural ordering xác định.

## 3. API thao tác ở hai đầu

`SequencedSet` nhận các phương thức từ `SequencedCollection`. Những phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `addFirst(E e)` | Thêm phần tử vào đầu encounter order |
| `addLast(E e)` | Thêm phần tử vào cuối encounter order |
| `getFirst()` | Lấy phần tử đầu mà không xóa |
| `getLast()` | Lấy phần tử cuối mà không xóa |
| `removeFirst()` | Lấy và xóa phần tử đầu |
| `removeLast()` | Lấy và xóa phần tử cuối |
| `reversed()` | Trả về view có encounter order đảo ngược |

Ví dụ với một danh sách nhãn ưu tiên:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

static void manageTags() {
    SequencedSet<String> tags = new LinkedHashSet<>();
    tags.addLast("java");
    tags.addLast("backend");
    tags.addLast("cloud");

    tags.addFirst("urgent");
    tags.addLast("java");

    System.out.println(tags);
    // [urgent, backend, cloud, java]

    System.out.println(tags.getFirst()); // urgent
    System.out.println(tags.getLast());  // java

    tags.removeFirst();
    tags.removeLast();
    System.out.println(tags);
    // [backend, cloud]
}
```

Điểm đáng chú ý là `java` đã tồn tại trong set. Gọi `addLast("java")` không tạo thêm một bản sao; với `LinkedHashSet`, phần tử đang có được chuyển đến cuối encounter order. Tương tự, `addFirst` có thể chuyển phần tử hiện có lên đầu.

`getFirst()`, `getLast()`, `removeFirst()` và `removeLast()` ném `NoSuchElementException` nếu set rỗng. Các thao tác thêm hoặc xóa ở hai đầu là optional operations; implementation không hỗ trợ thay đổi có thể ném `UnsupportedOperationException`.

## 4. Phân biệt add, addFirst và addLast

`Set.add(E)` thực hiện hợp đồng thêm phần tử của `Set`: nếu phần tử đã có, phương thức trả về `false` và không thêm bản sao. Với `LinkedHashSet`, lời gọi `add` thông thường cho một phần tử đã tồn tại không di chuyển phần tử đó trong encounter order.

`addFirst` và `addLast` có ý nghĩa vị trí rõ ràng. Với implementation hỗ trợ reposition như `LinkedHashSet`, nếu phần tử đã tồn tại, phương thức di chuyển phần tử đó đến đầu hoặc cuối thay vì tạo phần tử trùng lặp.

```java
static void compareInsertionOperations() {
    SequencedSet<String> names = new LinkedHashSet<>();
    names.addLast("An");
    names.addLast("Binh");
    names.addLast("Chi");

    names.add("An");
    System.out.println(names);
    // [An, Binh, Chi] — vị trí không đổi

    names.addLast("An");
    System.out.println(names);
    // [Binh, Chi, An] — An được chuyển xuống cuối
}
```

Vì vậy, hãy chọn `add` khi chỉ cần bảo đảm phần tử hiện diện; dùng `addFirst` hoặc `addLast` khi thứ tự đầu/cuối là một phần của yêu cầu nghiệp vụ.

## 5. reversed() tạo view có thứ tự ngược

`reversed()` trả về một `SequencedSet<E>` thể hiện cùng các phần tử theo encounter order ngược. Đây là view được liên kết với set gốc, không phải bản sao độc lập: thay đổi được phép qua view sẽ phản ánh vào set gốc và ngược lại.

```java
static void useReverseView() {
    SequencedSet<String> original = new LinkedHashSet<>();
    original.addLast("first");
    original.addLast("middle");
    original.addLast("last");

    SequencedSet<String> reverse = original.reversed();
    System.out.println(reverse);
    // [last, middle, first]

    reverse.addFirst("newest");
    System.out.println(original);
    // [first, middle, last, newest]
}
```

Trong view đảo ngược, `addFirst` tương ứng với thêm ở cuối set gốc; `addLast` tương ứng với thêm ở đầu set gốc. Các thao tác `getFirst`, `getLast`, `removeFirst` và `removeLast` cũng được hiểu theo hướng encounter order của view.

Khi chỉ cần duyệt ngược, có thể dùng trực tiếp:

```java
for (String name : original.reversed()) {
    System.out.println(name);
}
```

View có cùng đặc tính hỗ trợ thay đổi với implementation nền. Nếu set gốc không cho phép sửa đổi, không nên giả định view đảo ngược có thể sửa được.

## 6. Equality của Set không so sánh encounter order

Mặc dù `SequencedSet` có thứ tự duyệt xác định, nó vẫn giữ hợp đồng equality của `Set`: hai set bằng nhau nếu chứa cùng các phần tử, bất kể thứ tự encounter order. `hashCode()` cũng không biến thứ tự thành một phần của danh tính tập hợp.

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

static void compareSets() {
    SequencedSet<String> first =
            new LinkedHashSet<>(List.of("An", "Binh"));
    SequencedSet<String> second =
            new LinkedHashSet<>(List.of("Binh", "An"));

    System.out.println(first.equals(second)); // true
    System.out.println(List.copyOf(first).equals(List.copyOf(second)));
    // false: List equality có xét thứ tự
}
```

Đây là khác biệt quan trọng khi thiết kế nghiệp vụ. Nếu thứ tự chỉ phục vụ hiển thị hoặc duyệt, equality của set có thể phù hợp. Nếu thứ tự là một phần dữ liệu cần so sánh, hãy chuyển encounter order sang một kiểu có equality theo thứ tự, chẳng hạn `List`, hoặc tự định nghĩa phép so sánh tương ứng.

## 7. Các implementation và giới hạn cần biết

| Kiểu hoặc implementation | Encounter order | Lưu ý |
|---|---|---|
| `LinkedHashSet` | Thứ tự chèn, có thể điều chỉnh ở hai đầu | Hỗ trợ `addFirst` và `addLast`; phần tử đã có được di chuyển đến vị trí được yêu cầu |
| `TreeSet` / `SortedSet` | Thứ tự theo comparator hoặc natural ordering | Thứ tự do quy tắc sắp xếp quyết định; không hỗ trợ ép một phần tử lên đầu/cuối bằng `addFirst` hoặc `addLast` |
| `HashSet` | Không có encounter order được bảo đảm | Không phải implementation để dựa vào hợp đồng `SequencedSet` |
| Sequenced set không thể sửa đổi | Encounter order được implementation cung cấp | Các thao tác thay đổi có thể ném `UnsupportedOperationException` |

`SortedSet` mở rộng `SequencedSet` trong Java 21. Điều này cho phép dùng API chung để đọc phần tử đầu/cuối và duyệt theo chiều ngược, trong khi thứ tự vẫn do comparator quyết định. Những phương thức thêm ở hai đầu không phù hợp với một cấu trúc phải duy trì thứ tự sắp xếp nên có thể không được hỗ trợ.

Không phải mọi `Set` đều là `SequencedSet`. Nếu API chỉ khai báo kiểu trả về là `Set<E>`, caller không thể giả định có các phương thức `getFirst()`, `addFirst()` hoặc `reversed()`. Hãy dùng một implementation có encounter order được xác định và khai báo hợp đồng `SequencedSet` khi tính năng đó là yêu cầu của API.

## 8. Ví dụ thực tế: tập người nhận theo thứ tự ưu tiên

Một hàng đợi thông báo có thể cần loại trùng người nhận, nhưng vẫn giữ thứ tự xử lý. `SequencedSet` phù hợp khi một người nhận chỉ cần xuất hiện một lần và ứng dụng có thể đưa người nhận quan trọng lên đầu.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

static void prioritizeRecipients() {
    SequencedSet<String> recipients = new LinkedHashSet<>();
    recipients.addLast("team-a@example.test");
    recipients.addLast("team-b@example.test");
    recipients.addLast("team-c@example.test");

    // team-c đã có, nhưng cần xử lý trước.
    recipients.addFirst("team-c@example.test");

    for (String recipient : recipients) {
        System.out.println(recipient);
    }
    // team-c, team-a, team-b
}
```

Trong ứng dụng thật, phần tử có thể là ID hoặc value object người nhận thay vì email dạng chuỗi. Cần bảo đảm `equals()` và `hashCode()` của kiểu phần tử phản ánh đúng khái niệm trùng lặp của nghiệp vụ; nếu hai đối tượng có cùng ID nhưng `equals()` không nhận ra chúng là bằng nhau, set vẫn có thể chứa cả hai.

## 9. Khi nào nên dùng SequencedSet?

Dùng `SequencedSet` khi đồng thời cần:

- Loại bỏ phần tử trùng lặp theo equality của set.
- Duy trì một encounter order xác định để duyệt, hiển thị hoặc xử lý.
- Đọc, thêm, loại bỏ phần tử ở hai đầu hoặc duyệt ngược qua cùng một API.
- Truyền một hợp đồng rõ ràng cho caller rằng thứ tự duyệt là có ý nghĩa.

Không chọn `SequencedSet` chỉ vì cần một `Set` bất kỳ. Nếu thứ tự không có ý nghĩa, `Set` có thể đủ. Nếu cần nhiều phần tử trùng nhau hoặc equality phải phụ thuộc thứ tự, hãy chọn cấu trúc dữ liệu khác phù hợp hơn.

## 10. Sử dụng với Java 21

`SequencedSet` thuộc `java.util` và có từ Java 21. Ví dụ có thể biên dịch bằng release 21:

```bash
javac --release 21 -d out src/SequencedSetDemo.java
java -cp out SequencedSetDemo
```

Không cần `--enable-preview`. Nếu dự án dùng Maven hoặc Gradle, đặt compiler release/toolchain là 21 để sử dụng đúng API và kiểm tra mã nguồn theo Java 21.

## 11. Tài liệu tham khảo

- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Java SE 21 API — SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [Java SE 21 API — Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html)
