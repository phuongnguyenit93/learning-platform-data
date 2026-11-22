# Kiểm tra tính bất biến khi lớp chứa mảng hoặc tập hợp trong Java

## 1. Vấn đề cần giải quyết: field `private final` vẫn có thể chứa dữ liệu thay đổi

Khi một lớp Java được giới thiệu là **bất biến (*immutable*)**, ta kỳ vọng rằng **trạng thái có thể quan sát của một đối tượng đã xây dựng hoàn tất không bị thay đổi** bởi những thao tác được phép thực hiện từ bên ngoài.

Ví dụ:

```java
final class Exam {
    private final int[] scores;

    Exam(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }
}
```

Class `Exam` có vẻ “an toàn”: `final class`, field `private final`, không có method `setScores`. Nhưng nó **không bất biến**:

- Constructor giữ **cùng tham chiếu mảng** do caller truyền vào.
- Getter trả **chính mảng nội bộ**.
- Caller có thể sửa bất kỳ phần tử `scores[i]` nào, dù không được phép gán lại field `scores`.

Nguyên nhân: **`final` khóa phép gán lại field, không khóa nội dung đối tượng được tham chiếu**. `int[]`, `ArrayList`, `HashMap`, `HashSet` và nhiều kiểu khác vẫn là mutable objects.

Bài này không chỉ trình bày cách viết immutable class, mà chủ yếu trả lời câu hỏi thực hành:

> **Làm thế nào kiểm tra rằng một lớp chứa mảng hoặc tập hợp thật sự không bị thay đổi qua mọi đường tham chiếu từ bên ngoài?**

Sau bài, bạn có thể nhận diện các đường alias, thiết kế *defensive copy*, phân biệt unmodifiable view với snapshot, kiểm thử mảng nhiều chiều và collection chứa phần tử mutable, kiểm tra record/equals/hashCode, đồng thời viết các bài test Java 17+ có output xác định.

## 2. Định nghĩa kiểm thử: cái gì phải giữ nguyên?

Giả sử object được tạo tại thời điểm T0:

```text
Caller --input--> Constructor
                    |
                    v
               Object state S0
                    |
         các thao tác của caller
                    v
               Object state S1
```

Với object có hợp đồng bất biến, các thao tác bên ngoài được phép thực hiện không được biến **trạng thái logic của cùng object** từ S0 thành một giá trị khác. Để kiểm tra, bạn cần chọn **các quan sát đáng tin**:

- Getter trả primitive value hoặc immutable value: giá trị phải ổn định.
- Snapshot danh sách: các phần tử và thứ tự theo contract phải ổn định.
- Snapshot mảng: nội dung tại mỗi chỉ số phải ổn định.
- Các methods tính toán từ state, chẳng hạn `sum()`: kết quả phải ổn định khi input ban đầu không đổi theo contract.
- `equals`/`hashCode` của immutable value class: phải nhất quán theo cùng state logic.
- Các bất biến miền nghiệp vụ: không có null, duplicate hoặc giá trị ngoài phạm vi nếu constructor hứa điều đó.

**Không lấy một getter duy nhất làm bằng chứng cho toàn bộ object.** Nếu getter trả list copy nhưng một method khác trả mảng nội bộ hoặc một nested mutable element, object vẫn có thể thay đổi qua đường còn lại.

### Ba hướng tấn công quan trọng

1. **Input alias:** sửa mảng/list ban đầu sau khi constructor đã nhận nó.
2. **Output alias:** sửa mảng/list nhận lại từ getter.
3. **Nested alias:** sửa phần tử mutable hoặc collection lồng nhau dù outer collection là unmodifiable.

Thêm hai vấn đề nâng cao:

4. **State-sharing:** nhiều objects cùng giữ reference tới một component mutable không được kiểm soát.
5. **Concurrent modification:** dữ liệu nguồn đang bị thay đổi đúng lúc constructor kiểm tra/sao chép, hoặc object được công bố khi chưa tạo xong.

## 3. Phân biệt cấu trúc, phần tử và đồ thị đối tượng

Một `List` có thể chứa các `String` hoặc chứa các `StringBuilder`. Trong hai trường hợp, việc khóa cấu trúc list có ý nghĩa khác nhau:

```text
Trường hợp A:
List<String> --------> ["Java", "Core"]
                         |       |
                     immutable immutable

Trường hợp B:
List<StringBuilder> -> [ reference X ]
                              |
                              v
                       mutable builder
```

Nếu gọi `List.copyOf(...)`:

- Không thể gọi `add/remove/set` trên list kết quả.
- Nhưng nếu một phần tử là `StringBuilder`, nó vẫn có thể bị `append` qua reference đã có.
- Vì vậy bạn phải kiểm cả **container mutability** và **element mutability**.

Tương tự:

| Field | Rủi ro thường gặp |
| --- | --- |
| `private final int[] values` | Sửa các slots |
| `private final int[][] matrix` | Sửa outer/inner arrays, shallow copy |
| `private final List<String> names` | Input alias, getter alias, unmodifiable view backing |
| `private final List<StringBuilder> builders` | Nội dung phần tử mutable dù list unmodifiable |
| `private final Map<String, List<String>> data` | Mutable nested lists, alias ở map values |
| `private final Set<MutableKey> keys` | Phần tử mutate làm thay set equality/hash behavior |
| `record Data(int[] values)` | Record không tự clone component hoặc deep compare arrays |

**Đánh giá sâu dần từ object root:** Có thể đi từ field xuống collection, từ collection xuống element, rồi tới sub-element cho tới khi mọi đường mutable alias đã được chặn hoặc được kiểm soát theo contract.

## 4. Ví dụ đầu tiên: chứng minh lớp “final + private final” vẫn mutable

Tạo tệp **`BrokenArrayDemo.java`**:

```java
final class Exam {
    private final int[] scores;

    Exam(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }

    int firstScore() {
        return scores[0];
    }
}

public class BrokenArrayDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Exam exam = new Exam(input);

        System.out.println("before=" + exam.firstScore());

        input[0] = 99;
        System.out.println("after input=" + exam.firstScore());

        exam.scores()[0] = 77;
        System.out.println("after getter=" + exam.firstScore());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac BrokenArrayDemo.java
java BrokenArrayDemo
```

**Standard output:**

```text
before=10
after input=99
after getter=77
```

Hai phép thử có ý nghĩa khác nhau:

1. `input[0]=99` chứng minh **constructor leak**: caller giữ alias tới mảng nội bộ.
2. `exam.scores()[0]=77` chứng minh **getter leak**: caller có thể mutate mảng bên trong qua getter.

Ngay cả khi getter đổi sang trả `scores.clone()`, constructor vẫn có thể bị lỗi nếu giữ input gốc. Ngược lại, copy input ở constructor mà trả nguyên mảng nội bộ qua getter vẫn bị lỗi.

**Kết luận QA:** Muốn tuyên bố immutable, phải kiểm **cả đường vào và đường ra**.

## 5. Khắc phục cho mảng một chiều: copy ở cả hai ranh giới

Tạo **`SafeArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Exam {
    private final int[] scores;

    Exam(int[] input) {
        Objects.requireNonNull(input, "scores");

        int[] copy = input.clone();
        for (int score : copy) {
            if (score < 0) {
                throw new IllegalArgumentException("negative score");
            }
        }

        scores = copy;
    }

    int firstScore() {
        return scores[0];
    }

    int[] snapshot() {
        return scores.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(scores);
    }
}

public class SafeArrayDemo {
    public static void main(String[] args) {
        int[] original = {10, 20};
        Exam exam = new Exam(original);

        original[0] = 99;
        System.out.println("after input=" + exam);

        int[] copy = exam.snapshot();
        copy[1] = 77;
        System.out.println("after getter=" + exam);

        System.out.println("first=" + exam.firstScore());
    }
}
```

```bash
javac SafeArrayDemo.java
java SafeArrayDemo
```

```text
after input=[10, 20]
after getter=[10, 20]
first=10
```

Tại sao code bảo vệ được state?

- `input.clone()` tạo một mảng `int[]` khác reference với input.
- Validation duyệt **bản copy** dùng để lưu, không duyệt input rồi copy ở thời điểm khác. Điều này tránh một số lỗi check-then-copy trong code tuần tự; **không tự làm quá trình copy an toàn khi input đang bị sửa đồng thời**.
- Field `scores` là `private final`, nhận copy đúng một lần.
- `snapshot()` trả một clone mới; caller mutate clone không ảnh hưởng mảng nội bộ.
- `firstScore()` chỉ trả primitive, không lộ reference.

**Lưu ý:** `firstScore` đòi hỏi mảng không rỗng. Ví dụ dùng input có phần tử; nếu contract cho phép mảng rỗng, cần API `size()`/`at(index)` hoặc validation bắt buộc ít nhất một phần tử. Đó là một vấn đề thiết kế riêng, không làm mất ý nghĩa defensive copying.

## 6. Bảng kiểm đầu vào/đầu ra: hai phép thử độc lập

Một lớp `ImmutableArrayValue` được coi đạt kiểm tra alias cơ bản khi:

| Thử nghiệm | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| T1 — ingress | Giữ `input`, tạo object, sửa `input[0]` | Object không đổi |
| T2 — egress | Lấy getter array, sửa `getter[0]` | Object không đổi |
| T3 — identity | Gọi getter hai lần nếu API hứa copy | Hai arrays không cùng reference |
| T4 — value | Đọc `at(i)` hoặc snapshot | Giá trị giữ nguyên theo contract |
| T5 — validation | Constructor nhận dữ liệu sai | Ném lỗi; không trả instance hợp lệ |
| T6 — nested | Sửa array con/element mutable | Object không đổi nếu hợp đồng deep immutable |

**T3 không phải yêu cầu chung cho mọi immutable API.** Nếu getter trả chính một **immutable value object**, hai lần gọi có thể chia sẻ reference an toàn. Nhưng với getter có contract **trả mutable array snapshot**, so identity hai snapshots là phép thử hữu ích để phát hiện trả nhầm mảng nội bộ.

### Đừng chỉ test exception

Việc `list.add(...)` ném `UnsupportedOperationException` chứng minh caller không mutate **qua list reference đó** bằng `add`. Nó chưa chứng minh backing collection không thay từ reference khác hoặc elements không mutable.

## 7. Self-test hoàn chỉnh: kiểm tra hợp đồng mảng bất biến

Tạo tệp **`ArrayImmutabilitySelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Snapshot {
    private final int[] values;

    Snapshot(int[] source) {
        values = Objects.requireNonNull(source).clone();
    }

    int at(int index) {
        return values[index];
    }

    int[] values() {
        return values.clone();
    }
}

public class ArrayImmutabilitySelfTest {
    static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        Snapshot snapshot = new Snapshot(source);

        source[0] = 99;
        check(snapshot.at(0) == 1, "input alias");

        int[] exported = snapshot.values();
        exported[1] = 88;
        check(snapshot.at(1) == 2, "output alias");

        int[] firstRead = snapshot.values();
        int[] secondRead = snapshot.values();
        check(firstRead != secondRead, "fresh copies");

        check(Arrays.equals(snapshot.values(), new int[] {1, 2, 3}),
                "stable contents");

        System.out.println("array immutability PASS");
    }
}
```

```bash
javac ArrayImmutabilitySelfTest.java
java ArrayImmutabilitySelfTest
```

```text
array immutability PASS
```

`check(...)` ném `AssertionError` nếu phát hiện sai phạm; không phụ thuộc vào việc bật Java `-ea`. Đây là self-test chạy độc lập bằng `main`, không thay thế toàn bộ unit/property tests trong một dự án thật.

**Mở rộng test:** gọi constructor với null, mảng rỗng, kích thước lớn, giá trị không hợp lệ, và kiểm case nhiều threads chỉ khi API cam kết concurrent safety.

## 8. `int[][]`: outer clone không phải deep copy

Với mảng hai chiều:

```java
int[][] input = {{1, 2}, {3}};
int[][] shallow = input.clone();
```

`shallow` là outer array mới nhưng phần tử của nó vẫn chứa **references tới inner `int[]` arrays cũ**.

```text
input ───> outer X ─┬─> inner A [1,2]
                    └─> inner B [3]

shallow ──> outer Y ┬─> inner A [1,2]
                    └─> inner B [3]
```

Sửa `input[0][0]` cũng làm `shallow[0][0]` quan sát thay đổi. Do đó kiểm `input != shallow` **chưa đủ**.

### Chương trình phản chứng

Tệp **`ShallowMatrixDemo.java`**:

```java
import java.util.Arrays;

public class ShallowMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        int[][] shallow = input.clone();

        input[0][0] = 99;

        System.out.println(input != shallow);
        System.out.println(input[0] == shallow[0]);
        System.out.println(Arrays.deepToString(shallow));
    }
}
```

```bash
javac ShallowMatrixDemo.java
java ShallowMatrixDemo
```

```text
true
true
[[99, 2], [3]]
```

**Kết luận kiểm thử:** Nếu dữ liệu chứa references tới mutable child objects, phải thử **sửa một child** chứ không dừng ở việc outer object có identity khác.

## 9. Sao chép mảng hai chiều và kiểm thử mọi tầng

Tạo **`ImmutableMatrixDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Matrix {
    private final int[][] rows;

    Matrix(int[][] source) {
        Objects.requireNonNull(source, "source");
        rows = copyRows(source);
    }

    private static int[][] copyRows(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row " + i).clone();
        }
        return result;
    }

    int at(int row, int column) {
        return rows[row][column];
    }

    int[][] snapshot() {
        return copyRows(rows);
    }

    @Override
    public String toString() {
        return Arrays.deepToString(rows);
    }
}

public class ImmutableMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        Matrix matrix = new Matrix(input);

        input[0][0] = 99;
        input[1] = new int[] {88};

        System.out.println(matrix);

        int[][] exported = matrix.snapshot();
        exported[0][1] = 77;
        exported[1] = new int[] {66};

        System.out.println(matrix);
        System.out.println(matrix.at(1, 0));
    }
}
```

```bash
javac ImmutableMatrixDemo.java
java ImmutableMatrixDemo
```

```text
[[1, 2], [3]]
[[1, 2], [3]]
3
```

Ở đây sao chép **outer array và từng inner primitive array**:

- Tránh caller giữ alias vào source.
- Tránh getters làm lộ inner arrays.
- Giữ dữ liệu ổn định với cả sửa phần tử và thay row reference trong source/exported.
- Hỗ trợ mảng răng cưa (*jagged array*) vì mỗi row có độ dài riêng.

**Giới hạn:** Hàm `copyRows` kiểm null row và clone khi copy, nhưng không đồng bộ với một writer sửa source cùng lúc. Nếu source bị thay đồng thời, caller phải cung cấp snapshot ổn định hoặc thiết kế synchronization/ownership; chỉ `final`/`clone` không làm copy operation trở thành atomic với writer khác.

## 10. Mảng chứa object mutable: clone vẫn là shallow

Với:

```java
StringBuilder[] builders = {
        new StringBuilder("A")
};
StringBuilder[] copy = builders.clone();
```

`builders != copy` nhưng `builders[0] == copy[0]`.

### Runnable demo

Tệp **`MutableElementArrayDemo.java`**:

```java
public class MutableElementArrayDemo {
    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("A");
        StringBuilder[] input = {element};
        StringBuilder[] shallow = input.clone();

        element.append("B");

        System.out.println(input != shallow);
        System.out.println(input[0] == shallow[0]);
        System.out.println(shallow[0]);
    }
}
```

```bash
javac MutableElementArrayDemo.java
java MutableElementArrayDemo
```

```text
true
true
AB
```

Nếu muốn bảo đảm immutable **nội dung chuỗi**, thường đơn giản hơn **chuyển các mutable builders thành immutable `String` values** rồi lưu `String[]` hoặc `List<String>`.

Sao chép object graph tùy ý không thể giải quyết chỉ bằng `clone()`; cần quyết định semantics của mỗi nested mutable type.

## 11. Thiết kế lại representation: chuyển object mutable thành value bất biến

Tạo **`ImmutableTextBatchDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class TextBatch {
    private final String[] texts;

    TextBatch(StringBuilder[] input) {
        Objects.requireNonNull(input);
        texts = new String[input.length];

        for (int i = 0; i < input.length; i++) {
            StringBuilder item =
                    Objects.requireNonNull(input[i], "item");
            texts[i] = item.toString();
        }
    }

    String at(int index) {
        return texts[index];
    }

    String[] snapshot() {
        return texts.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(texts);
    }
}

public class ImmutableTextBatchDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        TextBatch batch = new TextBatch(
                new StringBuilder[] {source});

        source.append("B");
        System.out.println(batch);

        String[] copy = batch.snapshot();
        copy[0] = "C";

        System.out.println(batch);
        System.out.println(batch.at(0));
    }
}
```

```bash
javac ImmutableTextBatchDemo.java
java ImmutableTextBatchDemo
```

```text
[A]
[A]
A
```

Trong constructor, `toString()` tạo String representation không bị thay đổi bởi những lần `append` sau. Field lưu mảng `String[]`; getter trả clone. `String` immutable nên việc chia sẻ một `String` element an toàn theo content.

Đây là **snapshot về text content tại thời điểm đọc**. Nếu một thread khác mutate StringBuilder cùng lúc với `toString()`, ứng dụng phải xem xét thread-safety của input/handoff. Ví dụ giả định caller không sửa song song khi construction.

## 12. List đầu vào: giữ alias hay snapshot?

Một class giữ `private final List<String>` vẫn có thể bị thay đổi nếu constructor lưu reference tới mutable input.

Tệp **`ListInputAliasDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class BrokenPlaylist {
    private final List<String> songs;

    BrokenPlaylist(List<String> songs) {
        this.songs = songs;
    }

    List<String> songs() {
        return songs;
    }
}

public class ListInputAliasDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        BrokenPlaylist playlist = new BrokenPlaylist(input);
        input.add("B");

        System.out.println(playlist.songs());

        playlist.songs().remove("A");
        System.out.println(input);
    }
}
```

```bash
javac ListInputAliasDemo.java
java ListInputAliasDemo
```

```text
[A, B]
[B]
```

Kết quả cho thấy:

- Mutate input làm playlist quan sát phần tử mới.
- Mutate qua getter làm input bị thay.
- `private final` chỉ cố định reference `songs`, không cắt alias.

**Dữ liệu String không có lỗi:** `String` immutable. Lỗi nằm ở **mutable list container** và hai đường tham chiếu của nó.

## 13. `List.copyOf`: snapshot cấu trúc khi elements đã bất biến

Một cách phù hợp cho danh sách String:

```java
this.songs = List.copyOf(input);
```

`List.copyOf` tạo unmodifiable list theo API. Với một `ArrayList` mutable làm nguồn, thay đổi cấu trúc nguồn sau đó không phản ánh vào snapshot. Với String elements, ta có value components bất biến.

Tệp **`ImmutablePlaylistDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Playlist {
    private final List<String> songs;

    Playlist(List<String> input) {
        Objects.requireNonNull(input, "songs");
        songs = List.copyOf(input);
    }

    List<String> songs() {
        return songs;
    }
}

public class ImmutablePlaylistDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        Playlist playlist = new Playlist(input);
        input.add("B");

        System.out.println("source=" + input);
        System.out.println("snapshot=" + playlist.songs());

        try {
            playlist.songs().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add rejected");
        }
    }
}
```

```bash
javac ImmutablePlaylistDemo.java
java ImmutablePlaylistDemo
```

```text
source=[A, B]
snapshot=[A]
add rejected
```

**Kiểm nghiệm thành công vì cả hai đặc tính:**

1. **Không phản ánh cấu trúc mutable input** sau construction.
2. **Không cho mutate cấu trúc output** qua getter.

Vì type `String` immutable, test nested mutation cũng không có đường đi qua từng String object.

### Chính sách null của `List.copyOf`

`List.copyOf` **không chấp nhận null elements**. Constructor cần xác định đây là contract mong muốn hay đổi cách lưu để hỗ trợ null. Nếu caller cần phân biệt các phần tử null, phải thiết kế riêng; không lặng lẽ giả định mọi collection copy API giữ null.

`List.copyOf` có thể tối ưu bằng cách dùng lại một unmodifiable list input; **đừng test bắt buộc snapshot có identity khác mọi input** khi API không hứa điều đó. Test **hành vi cấu trúc không thể bị thay đổi**.

## 14. `Collections.unmodifiableList` là view, không nhất thiết là snapshot

Sai lầm dễ mắc:

```java
this.songs = Collections.unmodifiableList(input);
```

Caller không thể sửa list thông qua `songs` getter, nhưng có thể sửa list qua reference `input` còn giữ. **Unmodifiable view vẫn phản ánh backing list**.

Tệp **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);

        source.add("B");

        System.out.println("view=" + view);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

```text
view=[A, B]
copy=[A]
```

Nếu cần một snapshot nhưng dùng API wrapper cũ, có thể viết:

```java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(source));
```

Đây là **mảnh code** trong một method đã khai báo `source` và imports. Bản sao `new ArrayList<>(source)` tách backing structure; wrapper ngăn mutate nó qua exposed reference. Nhưng phần tử vẫn được copy **nông**.

**Test đủ hai hướng:** thử `source.add` và thử `snapshot.add`; một phép thử riêng lẻ có thể bỏ sót lỗi.

## 15. Không test identity của `List.of`/`List.copyOf` như một bảo đảm

Một số unmodifiable collections từ factory APIs được mô tả là **value-based**. Không được viết hợp đồng kiểu:

```java
// Không dùng làm tiêu chí bất biến:
// List.of("A") == List.of("A")
// List.copyOf(existing) != existing
```

API không hứa luôn tạo reference mới hoặc luôn dùng lại reference cũ. Cách kiểm đúng là **observable equality/content và hành vi mutation** theo contract.

Ví dụ:

```java
List<String> result = List.copyOf(source);

System.out.println(result.equals(List.of("A")));
```

là kiểm logical contents khi `source` ban đầu chứa `"A"`, không dựa vào implementation allocation.

Với input `ArrayList` mutable, sau khi `List.copyOf` hoàn tất bình thường, snapshot structure không phải view phản ánh những sửa đổi sau đó của ArrayList.

**Không dùng `==` trên hai collection instances để kết luận “immutable” hoặc “mutable”.** Hai biến có thể cùng trỏ một immutable object an toàn; hai mutable objects khác references vẫn mutable.

## 16. List chứa phần tử mutable: outer copy vẫn còn alias

Tạo **`MutableListElementDemo.java`**:

```java
import java.util.List;

public class MutableListElementDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        List<StringBuilder> values =
                List.copyOf(List.of(builder));

        builder.append("B");
        System.out.println(values.get(0));

        try {
            values.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("list structure locked");
        }
    }
}
```

```bash
javac MutableListElementDemo.java
java MutableListElementDemo
```

```text
AB
list structure locked
```

List không cho add, nhưng `StringBuilder` bên trong vẫn mutate qua alias `builder`. Kết quả này phát hiện **shallow immutability**.

### Kiểm thử phần tử mutable theo hai hướng

- **External element alias:** caller giữ object `builder` ban đầu, mutate nó và xem getter của immutable class có thay không.
- **Getter element leak:** caller lấy `list.get(0)` và gọi method mutate trên element rồi xem class có thay không.

Cả hai có thể xảy ra dù list wrapper là unmodifiable.

**Hướng khắc phục phổ biến:** biến các elements thành immutable values (`String`, immutable record với components phù hợp), hoặc tạo defensive copies sâu theo contract, hoặc không expose raw mutable elements.

## 17. Chuyển `List<StringBuilder>` thành `List<String>` bất biến

Tệp **`ImmutableNotesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> source) {
        Objects.requireNonNull(source);
        List<String> copy = new ArrayList<>();

        for (StringBuilder builder : source) {
            copy.add(Objects.requireNonNull(builder).toString());
        }

        lines = List.copyOf(copy);
    }

    List<String> lines() {
        return lines;
    }
}

public class ImmutableNotesDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        List<StringBuilder> input = new ArrayList<>();
        input.add(builder);

        Notes notes = new Notes(input);

        builder.append("B");
        input.add(new StringBuilder("C"));

        System.out.println("notes=" + notes.lines());

        try {
            notes.lines().set(0, "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("replacement blocked");
        }
    }
}
```

```bash
javac ImmutableNotesDemo.java
java ImmutableNotesDemo
```

```text
notes=[A]
replacement blocked
```

**Vì sao đủ cho ví dụ này?**

- Constructor chuyển từng mutable StringBuilder sang immutable String snapshot.
- Tạo unmodifiable List từ những strings ấy.
- Getter trả list vì cả structure và elements không cho caller đổi logical text content.
- Caller sửa hoặc thêm vào input gốc sau construction không làm `notes.lines()` đổi.

**Giới hạn:** Nếu StringBuilder được sửa đồng thời với `toString`, việc lấy snapshot cần cơ chế ownership/synchronization bên ngoài. Ví dụ chỉ giả định source ổn định trong lúc constructor đọc.

## 18. Tập hợp `Set`: unmodifiable structure chưa đủ nếu elements mutable

`Set.copyOf` có thể tạo unmodifiable set, nhưng **không đóng băng đối tượng phần tử**.

Một key mutable có `equals`/`hashCode` dựa vào state bị mutate sau khi đưa vào set có thể làm membership behavior không ổn định. Đây là hai vấn đề riêng:

1. **Bất biến của class chứa Set:** object phải không bị đổi state logic.
2. **Hợp đồng của hashing:** các phần tử dùng làm keys/elements trong hash-based structures phải có equality/hash phù hợp và ổn định trong thời gian tồn tại trong tập.

Đừng chỉ kiểm `set.add(...)` bị ném lỗi rồi kết luận toàn bộ Set object graph immutable.

### Ví dụ Set với String elements

Tệp **`ImmutableTagsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class Tags {
    private final Set<String> values;

    Tags(Set<String> input) {
        values = Set.copyOf(input);
    }

    boolean contains(String tag) {
        return values.contains(tag);
    }

    Set<String> snapshot() {
        return values;
    }
}

public class ImmutableTagsDemo {
    public static void main(String[] args) {
        Set<String> input = new HashSet<>();
        input.add("java");

        Tags tags = new Tags(input);
        input.add("oop");

        System.out.println(tags.contains("java"));
        System.out.println(tags.contains("oop"));

        try {
            tags.snapshot().add("new");
        } catch (UnsupportedOperationException ex) {
            System.out.println("tags locked");
        }
    }
}
```

```bash
javac ImmutableTagsDemo.java
java ImmutableTagsDemo
```

```text
true
false
tags locked
```

Không in trực tiếp `Set` bằng `toString()` rồi dự đoán thứ tự của nhiều phần tử — **Set iteration order có thể không được bảo đảm**. Ví dụ kiểm membership booleans để stdout ổn định.

## 19. `Map.copyOf` bảo vệ mapping structure, không deep-copy values

Tạo **`ImmutableRatesDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class Rates {
    private final Map<String, Integer> values;

    Rates(Map<String, Integer> input) {
        values = Map.copyOf(Objects.requireNonNull(input));
    }

    Integer forCode(String code) {
        return values.get(code);
    }

    Map<String, Integer> snapshot() {
        return values;
    }
}

public class ImmutableRatesDemo {
    public static void main(String[] args) {
        Map<String, Integer> input = new HashMap<>();
        input.put("A", 10);

        Rates rates = new Rates(input);
        input.put("A", 99);
        input.put("B", 20);

        System.out.println("A=" + rates.forCode("A"));
        System.out.println("B=" + rates.forCode("B"));

        try {
            rates.snapshot().put("C", 30);
        } catch (UnsupportedOperationException ex) {
            System.out.println("map locked");
        }
    }
}
```

```bash
javac ImmutableRatesDemo.java
java ImmutableRatesDemo
```

```text
A=10
B=null
map locked
```

- `Map.copyOf` cho snapshot của mappings từ một mutable map input theo API; sửa input sau đó không đổi map snapshot.
- Key `String` và value `Integer` trong ví dụ đều là immutable values.
- Caller không thể `put` vào map trả về.
- Getter `forCode` trả Integer immutable, không lộ mutable inner value.

**Chính sách null:** `Map.copyOf` từ chối null keys và values. Nếu nghiệp vụ cần cho phép null values, phải thiết kế semantics và storage khác chứ không giả định API giữ null.

## 20. Map chứa list values: phải snapshot cả map lẫn từng list

Một lỗi:

```java
Map<String, List<String>> snapshot = Map.copyOf(input);
```

Map structure có thể unmodifiable, nhưng các values kiểu `List<String>` **có thể là ArrayList mutable**. Caller sửa list value ban đầu, map snapshot có thể quan sát thay đổi.

### Cách kiểm thử lớp lồng nhau

Tạo **`NestedMapLeakDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedMapLeakDemo {
    public static void main(String[] args) {
        List<String> students = new ArrayList<>();
        students.add("An");

        Map<String, List<String>> source = new HashMap<>();
        source.put("A", students);

        Map<String, List<String>> outer = Map.copyOf(source);

        students.add("Binh");

        System.out.println(outer.get("A"));
        System.out.println(outer.get("A") == students);
    }
}
```

```bash
javac NestedMapLeakDemo.java
java NestedMapLeakDemo
```

```text
[An, Binh]
true
```

`Map.copyOf` không deep-copy nested lists. Test `students.add` phát hiện alias.

### Bản thiết kế cắt alias ở hai tầng

Tạo **`ImmutableGroupsDemo.java`**:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class Groups {
    private final Map<String, List<String>> members;

    Groups(Map<String, List<String>> source) {
        Objects.requireNonNull(source);

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry :
                source.entrySet()) {
            String key = Objects.requireNonNull(entry.getKey());
            List<String> value =
                    List.copyOf(Objects.requireNonNull(entry.getValue()));
            copy.put(key, value);
        }

        members = Map.copyOf(copy);
    }

    List<String> get(String group) {
        return members.get(group);
    }

    int groupCount() {
        return members.size();
    }
}

public class ImmutableGroupsDemo {
    public static void main(String[] args) {
        List<String> students =
                new java.util.ArrayList<>(List.of("An"));

        Map<String, List<String>> source = new HashMap<>();
        source.put("A", students);

        Groups groups = new Groups(source);

        students.add("Binh");
        source.put("B", List.of("Chi"));

        System.out.println("A=" + groups.get("A"));
        System.out.println("groups=" + groups.groupCount());

        try {
            groups.get("A").add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("nested list locked");
        }
    }
}
```

```bash
javac ImmutableGroupsDemo.java
java ImmutableGroupsDemo
```

```text
A=[An]
groups=1
nested list locked
```

Bản sửa snapshot:

1. `Map` structure bằng `Map.copyOf`.
2. Mỗi `List<String>` value bằng `List.copyOf`.
3. Mỗi `String` key/element immutable.

Do vậy không lộ alias có thể mutate logical state trong ví dụ. Nếu values chứa mutable objects thay cho String, còn phải snapshot từng element.

## 21. Getter trả `Map`/`List`: nên trả trực tiếp hay trả copy?

**Không có câu trả lời chỉ dựa vào tên getter.** Phụ thuộc vào **loại object thực tế** được lưu.

| Internal field | Getter trả field trực tiếp có an toàn về bất biến? |
| --- | --- |
| `int[]` mutable array | **Không** |
| `ArrayList<String>` mutable | **Không** |
| `Collections.unmodifiableList(source)` view trên mutable source còn alias | **Không bảo đảm** |
| `List.copyOf(List<String>)` với String immutable | Thường **có**, theo structural immutability |
| `List.copyOf(List<StringBuilder>)` | **Không**, elements mutable |
| `Map.copyOf(Map<String,Integer>)` | Thường **có**, keys/values immutable |
| `Map.copyOf(Map<String,List<String>>)` nếu list values mutable | **Không** |
| Value object bất biến đã thiết kế đúng | Có thể trả reference trực tiếp |

Trả một **immutable object reference** nhiều lần không tự vi phạm bất biến. Defensive copying chỉ thực sự cần tại **mutable boundary**; sao chép vô tội vạ khiến code phức tạp và tốn tài nguyên mà không đem lại lợi ích nếu dữ liệu đã bất biến.

## 22. Kiểm tra qua `Iterator`, `ListIterator` và `Map.Entry`

Getter có thể không trả collection trực tiếp mà trả iterator/entry view. Đừng quên chúng cũng là **đường truy cập** tới nội bộ.

Ví dụ nếu method:

```java
Iterator<String> iterator() {
    return internalMutableList.iterator();
}
```

thì caller có thể gọi `iterator.remove()` ở các trạng thái được iterator hỗ trợ, làm thay đổi backing list.

Với `ListIterator`, các methods `set`/`add` trên iterator của mutable list cũng có thể sửa structure.

Với `Map.Entry<K,V>` từ mutable `Map.entrySet()`, `entry.setValue(...)` có thể thay mapping trong nhiều implementations.

**Bộ kiểm test phải nhìn mọi public API:** getter, iterator, stream, subList/view, map entry, arrays trả từ conversion methods, callback nhận mutable object. Không chỉ tìm các methods có tên `set...`.

Khi lưu unmodifiable snapshot được tạo bằng `List.copyOf`/`Map.copyOf`, các operations mutate qua iterator/entry views thích hợp cũng bị từ chối theo contract của unmodifiable structures. Nhưng **nested mutable element** vẫn có thể bị sửa qua iterator trả element.

### Kiểm tra cụ thể trên unmodifiable list

Tệp **`ImmutableIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.List;

public class ImmutableIteratorDemo {
    public static void main(String[] args) {
        List<String> values = List.copyOf(List.of("A", "B"));
        Iterator<String> iterator = values.iterator();

        System.out.println(iterator.next());

        try {
            iterator.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println("iterator removal blocked");
        }

        System.out.println(values.size());
    }
}
```

```bash
javac ImmutableIteratorDemo.java
java ImmutableIteratorDemo
```

```text
A
iterator removal blocked
2
```

Iterator đã đi qua phần tử đầu tiên nên không có lỗi “remove before next”; exception thể hiện mutation qua iterator bị chặn.

## 23. Record có array/list component: không tự động deep immutable

Java `record` có final component fields và accessors sinh tự động, nhưng không tự copy mutable components.

Tạo **`BrokenRecordDemo.java`**:

```java
record Numbers(int[] values) {
}

public class BrokenRecordDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Numbers numbers = new Numbers(source);

        source[0] = 99;
        System.out.println(numbers.values()[0]);

        numbers.values()[1] = 77;
        System.out.println(source[1]);
    }
}
```

```bash
javac BrokenRecordDemo.java
java BrokenRecordDemo
```

```text
99
77
```

Record không tự clone constructor parameter và accessor `values()` trả array reference. Code là một phản chứng: records **shallowly final**, không automatically deeply immutable.

Thêm vấn đề: record-generated `equals`/`hashCode` cho array component dùng component equality semantics theo array references; hai record chứa arrays khác reference nhưng cùng elements không tự equal theo content.

## 24. Record an toàn hơn nhờ compact constructor và defensive accessor

Tệp **`SafeRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeNumbers(int[] values) {
    SafeNumbers {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        SafeNumbers numbers = new SafeNumbers(input);

        input[0] = 99;

        int[] exported = numbers.values();
        exported[1] = 77;

        System.out.println(numbers);
        System.out.println(numbers.at(0));
    }
}
```

```bash
javac SafeRecordDemo.java
java SafeRecordDemo
```

```text
[1, 2]
1
```

Trong compact constructor, `values = values.clone()` thay giá trị constructor parameter trước khi nó được gán cho component field theo rules. Accessor tự viết trả clone.

**Tách hai tiêu chí kiểm tra:**

- **Immutability:** Input/output mutation không ảnh hưởng record state → ví dụ đạt.
- **Content equality:** Hai SafeNumbers chứa hai arrays khác identity nhưng cùng elements có equal hay không? Generated equals **không tự so phần tử mảng**, nên phải custom equals/hashCode nếu domain yêu cầu content-based equality.

Không kết luận “immutable” chỉ vì record class có `final` fields hoặc vì `record` tạo sẵn equals.

## 25. Kiểm tra `equals` và `hashCode` của lớp chứa mảng

Nếu một immutable value class có nghĩa bằng nhau theo **nội dung mảng**, nên xác định equals/hashCode theo cùng dữ liệu.

Tệp **`ImmutableVectorEqualityDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Vector {
    private final int[] values;

    Vector(int[] input) {
        values = Objects.requireNonNull(input).clone();
    }

    int[] snapshot() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Vector vector)) {
            return false;
        }
        return Arrays.equals(values, vector.values);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}

public class ImmutableVectorEqualityDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Vector first = new Vector(input);
        Vector second = new Vector(new int[] {1, 2});

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(
                first.hashCode() == second.hashCode());

        input[0] = 99;
        System.out.println(first.equals(second));

        int[] exported = first.snapshot();
        exported[1] = 77;
        System.out.println(first.equals(second));
    }
}
```

```bash
javac ImmutableVectorEqualityDemo.java
java ImmutableVectorEqualityDemo
```

```text
false
true
true
true
true
```

Bộ test kiểm:

1. Hai instances khác references.
2. Chúng equal theo contents khi class chủ động định nghĩa.
3. Equal objects có equal hash codes.
4. Mutate input gốc không đổi equals outcome.
5. Mutate snapshot getter không đổi equals outcome.

**Ghi nhớ:** Với nested arrays, nếu dùng `Arrays.deepEquals` thì cũng phải chọn hash function phù hợp như `Arrays.deepHashCode` theo type/contract. Đừng dùng `Arrays.equals` nhưng hash theo identity của array, hoặc ngược lại.

## 26. Set với mutable element: rủi ro khác với mutate cấu trúc Set

Xét một `HashSet<MutableKey>`:

```java
class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && java.util.Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}
```

Ngay cả khi tạo:

```java
Set<MutableKey> snapshot = Set.copyOf(source);
```

thì `MutableKey` elements vẫn có thể đổi `code` qua reference có sẵn. Hash/equality của keys đổi theo, có thể làm lookup behavior không đáng tin nếu collection implementation phụ thuộc stable hash/equality.

Vì vậy với một **immutable set of values**, nên lưu **immutable element types** (ví dụ `record Key(String code)` với String component), hoặc deep-snapshot dữ liệu cần thiết sang type bất biến.

**Không viết một test chỉ đòi `contains(...)` nhất định false/true sau khi cố tình phá hash-key invariants**: kết quả phụ thuộc cách triển khai và trạng thái nội bộ. Test nên chứng minh thiết kế mới không cho key state mutate theo lối ấy.

## 27. Deep copy và định nghĩa “sâu” phải bám theo miền dữ liệu

Deep copy không chỉ là “clone thêm một lần”.

Giả sử object A có Map trỏ Lists, Lists trỏ MutableElements, MutableElements trỏ buffers. Bạn phải xác định:

- Những object nào thuộc **observable state**?
- Những object nào mutable?
- Những aliases nào caller có thể giữ?
- Có cần **giữ sharing** giữa các elements khi copy không?
- Có cycles trong object graph không?
- Có external resources (socket, thread, file) không thể clone theo nghĩa “giá trị” không?
- Có thể chuyển sang immutable representation đơn giản hơn không?

### Hai chiến lược

**Chiến lược A — immutable components từ sớm:** Normalize/map mỗi input thành immutable strings/records, sau đó `List.copyOf`/`Map.copyOf`. Thường dễ chứng minh và test.

**Chiến lược B — defensive deep copy có quy ước:** Copy array/list/map ở mỗi tầng và copy mutable leaf objects. Phải quan tâm cycles, shared identity, exception, concurrent mutation.

Không nên gọi `Object.clone()` là giải pháp “deep immutable” mặc định. Semantics clone của mỗi class khác nhau; có nhiều kiểu không hỗ trợ clone hoặc không cung cấp safe clone contract.

## 28. Iterator/stream và snapshot: đừng lẫn thời điểm quan sát

Nếu class trả `Stream` trực tiếp được tạo từ backing mutable collection, một lần stream traversal có thể quan sát những thay đổi của backing collection hoặc gặp concurrent modification theo đặc điểm collection. Điều này có thể làm API “giống getter” nhưng không thực sự snapshot.

Nếu object muốn immutable snapshot API, cách đơn giản là **giữ unmodifiable snapshot từ construction** rồi trả stream từ snapshot đó.

Ví dụ:

```java
final class Tags {
    private final java.util.List<String> tags;

    Tags(java.util.List<String> input) {
        tags = java.util.List.copyOf(input);
    }

    java.util.stream.Stream<String> stream() {
        return tags.stream();
    }
}
```

`Tags` lưu list snapshot; mỗi stream duyệt immutable String elements ở snapshot. Tuy nhiên stream là object tiêu thụ một lần theo API, và trả stream không phải lúc nào cũng cần thiết: có thể trả `List<String>` nếu contract thích hợp.

**Trong tests**, so outputs qua `List.copyOf(stream.toList())` hoặc operations deterministic, tránh dựa vào thứ tự của `Set`/`HashMap` khi không có ordered contract.

## 29. Concurrent modification trong lúc constructor copy: ranh giới mà `final` không tự giải quyết

Một constructor:

```java
this.items = List.copyOf(input);
```

có thể là lựa chọn rất tốt khi **input không bị mutate đồng thời trong quá trình copy**. Nhưng nếu một thread khác đang add/remove trong mutable input:

- Có thể tạo ra race không được contract input collection cho phép.
- Copy có thể thất bại hoặc nhận một trạng thái không nhất quán theo loại collection.
- Một validation diễn ra trước copy có thể không còn áp dụng cho dữ liệu thực được copy.
- `final` trên field kết quả không sửa được lỗi đã xảy ra trong lúc đọc source.

**Các hướng kiểm soát:**

1. Caller chuyển một **ổn định snapshot** hoặc chỉ chuyển immutable input.
2. Caller/constructor dùng một synchronization protocol chung với writers cho đoạn snapshot.
3. Sử dụng API có contract snapshot phù hợp theo loại concurrent collection khi yêu cầu.
4. Sau copy, validate **chính dữ liệu sẽ lưu**, không chỉ nguồn trước copy.

Không dùng một stress test chạy vài lần không thấy race để chứng minh thread safety tuyệt đối. Cần thiết kế happens-before/ownership semantics rõ ràng.

## 30. Kiểm tra object công bố quá sớm trong constructor

Một class có thể snapshot đúng list nhưng vẫn không an toàn nếu công bố `this` trước khi khởi tạo xong.

Ví dụ anti-pattern:

```java
class Registry {
    static final java.util.List<Object> ALL =
            new java.util.ArrayList<>();
}

class UnsafeCourse {
    private final java.util.List<String> topics;

    UnsafeCourse(java.util.List<String> input) {
        Registry.ALL.add(this); // Công bố object quá sớm.
        topics = java.util.List.copyOf(input);
    }
}
```

Đây là **code minh họa hành vi rủi ro**, không có `main`. Compiler có thể chấp nhận assignment của final field đúng trước constructor return, nhưng một nơi khác có reference `this` trong lúc `topics` chưa được gán và construction chưa hoàn tất.

**Checklist an toàn:**

- Không đăng ký `this` trong constructor trước khi hoàn tất.
- Không khởi động threads/callbacks có thể quan sát instance chưa hoàn thành.
- Không gọi overridable methods dựa trên subclass state từ superclass constructor.
- Chỉ giao reference ra ngoài khi invariants đã được thiết lập.
- Với concurrency, dùng publication mechanism đúng contract.

**Đừng đánh đồng:** defensive copy bảo vệ *data aliasing*; proper construction/publication bảo vệ *object lifecycle/visibility*. Một immutable object đáng tin cần cả hai theo hoàn cảnh.

## 31. Property-based suy luận: bao phủ nhiều mutation paths

Một bài test cơ bản chỉ sửa `input[0]`. Điều đó không bắt được mọi lỗi trong object graph. Cách mở rộng có hệ thống là lập **ma trận đối tượng và đường truy cập**:

| Loại state | Trước khi tạo | Sau khi tạo qua input alias | Qua getter | Qua nested element |
| --- | --- | --- | --- | --- |
| `int[]` | Copy giá trị | `input[i]=...` | `getter[i]=...` | Không áp dụng |
| `int[][]` | Copy outer + inner | Sửa `input[i][j]`; thay row | Sửa `getter[i][j]`; thay row | Inner arrays |
| `List<String>` | Snapshot structure | `source.add/remove` | `getter.add/set/remove` | String immutable |
| `List<Mutable>` | Snapshot elements | Sửa element object gốc | Sửa element lấy từ getter | Nested fields |
| `Set<ImmutableKey>` | Snapshot structure | `source.add/remove` | `getter.add/remove` | Keys immutable |
| `Map<K,List<V>>` | Copy map + values | Mutate map/list gốc | Mutate returned map/list | Mutable V nếu có |
| Record + `int[]` | Copy constructor component | Mutate source array | Mutate accessor output | Mảng |

### Cách kiểm nếu dùng JUnit

Bộ test tương đương có thể được viết bằng assertions của JUnit 5 như `assertEquals`, `assertArrayEquals`, `assertThrows`. Nhưng để tài liệu này **chạy ngay với JDK 17 không cần dependency**, các ví dụ dùng helper `check` và `main`.

Bất cứ framework nào cũng phải kiểm cùng **hành vi**, không chỉ tên annotation test.

## 32. Bộ kiểm thử tổng hợp cho một lớp chứa cả mảng lẫn tập hợp

Tạo **`ImmutabilityAuditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.Objects;

final class CourseData {
    private final int[] scores;
    private final List<String> topics;
    private final Map<String, List<String>> groups;

    CourseData(int[] scores, List<String> topics,
               Map<String, List<String>> groups) {
        this.scores = Objects.requireNonNull(scores).clone();
        this.topics = List.copyOf(Objects.requireNonNull(topics));

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry :
                Objects.requireNonNull(groups).entrySet()) {
            String key = Objects.requireNonNull(entry.getKey());
            List<String> value =
                    List.copyOf(Objects.requireNonNull(entry.getValue()));
            copy.put(key, value);
        }
        this.groups = Map.copyOf(copy);
    }

    int[] scores() {
        return scores.clone();
    }

    List<String> topics() {
        return topics;
    }

    List<String> group(String name) {
        return groups.get(name);
    }

    int groupCount() {
        return groups.size();
    }
}

public class ImmutabilityAuditDemo {
    static void check(boolean ok, String test) {
        if (!ok) {
            throw new AssertionError(test);
        }
    }

    public static void main(String[] args) {
        int[] scores = {10, 20};
        List<String> topics = new ArrayList<>(List.of("Class"));
        List<String> students = new ArrayList<>(List.of("An"));
        Map<String, List<String>> groups = new HashMap<>();
        groups.put("A", students);

        CourseData data = new CourseData(scores, topics, groups);

        // Attack 1: Mutate caller-owned inputs.
        scores[0] = 99;
        topics.add("Object");
        students.add("Binh");
        groups.put("B", List.of("Chi"));

        check(Arrays.equals(data.scores(), new int[] {10, 20}),
                "score ingress");
        check(data.topics().equals(List.of("Class")),
                "topics ingress");
        check(data.group("A").equals(List.of("An")),
                "nested list ingress");
        check(data.groupCount() == 1, "map ingress");

        // Attack 2: Mutate returned array.
        int[] exported = data.scores();
        exported[1] = 77;
        check(data.scores()[1] == 20, "score egress");

        // Attack 3: Mutate exposed immutable lists.
        boolean topicsRejected = false;
        try {
            data.topics().add("Invalid");
        } catch (UnsupportedOperationException ex) {
            topicsRejected = true;
        }
        check(topicsRejected, "topics egress");

        boolean groupRejected = false;
        try {
            data.group("A").set(0, "Other");
        } catch (UnsupportedOperationException ex) {
            groupRejected = true;
        }
        check(groupRejected, "group egress");

        check(data.topics().equals(List.of("Class")),
                "topics final state");
        check(data.group("A").equals(List.of("An")),
                "group final state");

        System.out.println("immutability audit PASS");
    }
}
```

```bash
javac ImmutabilityAuditDemo.java
java ImmutabilityAuditDemo
```

```text
immutability audit PASS
```

**Vì sao audit này có giá trị hơn một getter test đơn lẻ?**

1. Có cả primitive array và nested collections.
2. Mutate **tất cả input aliases** giữ từ trước.
3. Kiểm array getter trả copy, không lộ mảng nội bộ.
4. Kiểm List/Map-derived lists từ getter chặn mutator operations.
5. Kiểm tổng thể cuối cùng vẫn như snapshot tại construction.

**Giới hạn được tuyên bố rõ:** Elements trong `topics` và `groups` là String immutable; code này **không hỗ trợ** arbitrary mutable elements. Nếu thay type thành `List<StringBuilder>` mà chỉ dùng `List.copyOf`, cần bài test mutate nested builder và chiến lược copy mới.

## 33. Kiểm tra lỗi ở constructor: dữ liệu thiếu và null elements

Một immutable class phải đảm bảo **không trả về instance hợp lệ giả** khi input vi phạm contract.

Ví dụ với `List.copyOf`:

- `null` collection reference → lỗi.
- `null` element trong collection → lỗi.
- Những inputs có data validity riêng phải được constructor validate, ví dụ điểm số âm hoặc duplicate codes.
- Snapshot không thay thế validation: list copy được vẫn có thể chứa String rỗng nếu domain không cho phép.

### Demo: validation trước khi công bố

Tệp **`ImmutableValidatedNamesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Names {
    private final List<String> values;

    Names(List<String> input) {
        Objects.requireNonNull(input);

        List<String> copy = new ArrayList<>(input);
        for (String item : copy) {
            if (item == null || item.isBlank()) {
                throw new IllegalArgumentException("invalid name");
            }
        }

        values = List.copyOf(copy);
    }

    List<String> values() {
        return values;
    }
}

public class ImmutableValidatedNamesDemo {
    public static void main(String[] args) {
        Names ok = new Names(List.of("An", "Binh"));
        System.out.println(ok.values());

        try {
            new Names(List.of("An", ""));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input rejected");
        }
    }
}
```

```bash
javac ImmutableValidatedNamesDemo.java
java ImmutableValidatedNamesDemo
```

```text
[An, Binh]
invalid input rejected
```

Constructor tạo `ArrayList` copy trước, validate trên chính copy dùng để lưu, rồi chuyển thành unmodifiable list. Nếu input bị mutate đồng thời trong lúc copy, vẫn cần synchronization/handoff contract riêng.

**Không quên tính nguyên tử ở cấp nghiệp vụ:** Nếu constructor còn ghi file, đăng ký listener hoặc gọi external API rồi mới ném exception, sẽ có side effects không tự rollback. Immutable fields không bảo đảm transactional construction.

## 34. Không mọi phép mutate đều phải ném exception

Có ít nhất hai cách an toàn:

**(A) Getter trả một mutable copy riêng.** Caller sửa bản copy được phép, nhưng internal object không đổi.

```java
int[] values() {
    return internal.clone();
}
```

**(B) Getter trả một immutable/unmodifiable snapshot.** Caller gọi mutator có thể bị từ chối.

```java
List<String> values() {
    return List.copyOf(internal);
}
```

Vì vậy không nên viết một test chung luôn đòi mọi mutation ở returned value đều ném `UnsupportedOperationException`. Với mảng, `copy[0] = 10` được phép; **điều quan trọng là nó không làm internal state thay đổi**.

Các test phải xuất phát từ **contract của getter**:

- Nếu getter hứa fresh mutable snapshot → phép sửa có thể thành công trên snapshot, object bất biến không đổi.
- Nếu getter hứa unmodifiable view/snapshot → mutators bị cấm nhưng cần kiểm backing data không bị ngoại lực sửa.
- Nếu getter hứa immutable value reference → sharing cùng reference có thể là đúng, không cần copy vô ích.

## 35. Thử phản ví dụ trước khi tin các modifier

Một anti-pattern khá phổ biến:

```java
final class Configuration {
    private final List<String> names;

    Configuration(List<String> names) {
        this.names = names;
    }

    List<String> names() {
        return java.util.Collections.unmodifiableList(names);
    }
}
```

Getter **chặn sửa qua returned view**, nhưng constructor đã giữ mutable input alias. Caller vẫn có thể sửa `input.add(...)` sau khi tạo.

Để **bắt lỗi**, test phải:

1. Truyền một `ArrayList` thật sự mutable.
2. Ghi nhận state sau construction.
3. Mutate `input`.
4. Đọc getter lần nữa.
5. So với expected snapshot, không chỉ thử `getter.add`.

**Một ví dụ khác:** constructor copy list structure nhưng elements là mutable objects; phải sửa element từ reference caller giữ.

Bài toán immutable không được giải bằng “thêm `final` cho đủ” hoặc “bọc getter bằng `unmodifiableList`” mà cần kiểm toàn bộ references có quyền mutate observable state.

## 36. Kiểm thử `equals`/`hashCode` không đổi sau các phép mutate bên ngoài

Với một **value class bất biến**, nếu equality/hashCode dựa trên trạng thái logic thì kết quả phải ổn định khi caller cố sửa input hay snapshots.

Ví dụ `Vector` ở mục trước:

```java
Vector a = new Vector(new int[] {1, 2});
Vector b = new Vector(new int[] {1, 2});
```

Đây là mảnh code sử dụng class `Vector` đã khai báo trong ví dụ runnable ở mục 25.

Bạn có thể ghi nhận:

- `a.equals(b)` ban đầu.
- `a.hashCode()` ban đầu.
- Sau đó sửa mảng nguồn đã truyền vào `a` (nếu còn giữ reference).
- Sửa mảng mà getter `a.snapshot()` trả ra.
- Kiểm lại equality/hashCode và nội dung.

**Nhưng:** nếu class chủ ý dùng **identity equality** thay vì value equality, việc hashCode/equals không so contents không tự làm nó mutable. Hãy phân biệt **hợp đồng bất biến** với **hợp đồng value equality**.

## 37. Những sai lầm phổ biến

| Sai lầm | Vì sao không đủ? | Phép kiểm cần bổ sung |
| --- | --- | --- |
| “Field `private final int[]` là immutable” | Array slots vẫn mutable | Sửa input và getter array |
| “`final class` ngăn mọi mutation” | Methods/objects bên trong vẫn mutable | Audit tất cả mutation paths |
| “Getter trả clone là đủ” | Constructor có thể giữ input alias | Mutate source sau construction |
| “Constructor clone là đủ” | Getter có thể trả internal reference | Mutate getter return |
| “`matrix.clone()` là deep copy” | Inner arrays vẫn alias | Sửa `source[i][j]` |
| “`array.clone()` deep copy elements” | Object references vẫn chia sẻ | Mutate nested mutable element |
| “`List.copyOf` deep-freeze elements” | Chỉ unmodifiable structure | Mutate element alias |
| “`unmodifiableList(source)` là snapshot” | Backing source vẫn thay | Mutate source, đọc view |
| “Không gọi được `add` nên object bất biến” | Có thể mutable qua alias khác | Test ingress/nested aliases |
| “Getter luôn phải tạo object mới” | Có thể chia sẻ immutable object an toàn | Kiểm behavior, không `==` bắt buộc |
| “Mọi mutation qua getter phải ném lỗi” | Getter mutable copy có thể được sửa an toàn | Kiểm original không đổi |
| “`Set.copyOf` làm mutable key bất biến” | Key object vẫn mutable | Test nested key semantics |
| “`Map.copyOf` clone nested lists” | Values chia sẻ references | Mutate backing nested list |
| “Record chứa array tự deep immutable” | Accessor/constructor có thể giữ alias | Test record input và output |
| “Record array equals tự so contents” | Arrays default identity equality | Custom equals/hash nếu cần |
| “Set iteration order cố định” | Không được bảo đảm chung | Test membership/size thay vì string order |
| “Chạy một stress test không lỗi là thread-safe” | Race phụ thuộc lịch chạy | Thiết kế synchronization/ownership |
| “Copy sau validate luôn an toàn đồng thời” | Source có thể đổi giữa steps | Snapshot ổn định; validate snapshot |
| “`final` bảo vệ object công bố giữa constructor” | `this` có thể escape sớm | Audit constructor/callback/thread |
| “Immutable object bắt buộc có custom equals” | Equality tùy domain | Quyết định contract riêng |
| “Chỉ test happy path là đủ” | Null/blank/invalid có thể lọt | Test constructor failure |
| “`HashSet` chứa mutable key vẫn an toàn” | Equality/hash có thể thay | Immutable key và tests |
| “Deep copy luôn là clone cả graph” | Có cycles/resources/ownership | Xác định semantics của graph |

## 38. Bài tập thực hành

**Bài 1.** Viết class chứa `private final byte[] payload`. Hãy lập hai test chứng minh caller không mutate qua input hoặc getter.

*Hướng giải:* Constructor lưu `payload.clone()`, getter trả `payload.clone()`; sau đó mutate input và clone getter, đọc checksum/`Arrays.equals` để xác minh original giữ nguyên.

**Bài 2.** Với `List<StringBuilder>`, dùng `List.copyOf` đã đủ chưa?

*Đáp án:* Chưa. Mutate StringBuilder từ alias ngoài vẫn đổi text. Chuyển thành List<String> snapshots hoặc deep-copy mutable leaves phù hợp.

**Bài 3.** Với `Map<String,List<String>>`, đã dùng `Map.copyOf`, còn gì chưa đủ?

*Đáp án:* Cần snapshot mỗi inner list bằng `List.copyOf` hoặc cơ chế tương đương.

**Bài 4.** Với `int[][]`, tại sao chỉ kiểm `input != copied` không chứng minh immutable?

*Đáp án:* Inner arrays vẫn có thể cùng reference. Phải kiểm `input[i] != copied[i]` khi hợp đồng yêu cầu copy và mutate nested slots.

**Bài 5.** `Collections.unmodifiableList(input)` có cho caller `add` qua view không? Có chặn người giữ `input` gốc không?

*Đáp án:* Qua view thì bị chặn; không chặn mutation thông qua backing input reference.

**Bài 6.** `List.copyOf` trả list có thể dùng lại reference input không?

*Đáp án:* API có thể tận dụng unmodifiable inputs; không được giả định identity khác luôn. Kiểm semantic immutability, không kiểm reference identity không được bảo đảm.

**Bài 7.** Tạo record có `int[]`. Hai hướng mutation nào cần test?

*Đáp án:* Sửa constructor argument và sửa array do accessor trả về. Nếu dùng record-generated equality cần kiểm array semantics.

**Bài 8.** Mảng trả từ getter được phép sửa mà object không đổi; đây có vi phạm bất biến không?

*Đáp án:* Không. Getter có thể trả mutable defensive copy độc lập.

**Bài 9.** Tại sao `HashSet<MutableKey>` có thể hỏng semantics ngay cả khi Set structure không sửa?

*Đáp án:* Mutable key fields thay `equals/hashCode` trong lúc nằm trong collection.

**Bài 10.** Lớp chứa `List<LocalDate>` và giữ snapshot `List.copyOf` có rủi ro mutable element như StringBuilder không?

*Đáp án:* `LocalDate` là immutable value type; với đúng contract và input snapshot ổn định, không có đường mutate element giống StringBuilder.

**Bài 11.** Nếu constructor validate input list rồi một thread khác sửa source trước khi `List.copyOf`, điều gì có thể xảy ra?

*Đáp án:* Validation không còn áp dụng cho đúng dữ liệu được lưu; cần copy ổn định, validate snapshot và synchronization/ownership khi concurrent mutation.

**Bài 12.** Một class bất biến có thể có getter trả chính `List.copyOf` stored list không?

*Đáp án:* Có khi elements/keys/values là immutable theo contract và snapshot không có đường mutable alias làm đổi observable state.

**Bài 13.** Với `Map<String, MutableValue>`, `Map.copyOf` có đủ không?

*Đáp án:* Không. Cần copy/convert mỗi mutable value thành immutable representation hoặc thiết kế visibility/ownership khác.

**Bài 14.** Một array of mutable objects có cần clone mỗi element không?

*Đáp án:* Nếu caller vẫn có khả năng mutate elements và điều đó đổi observable state, phải copy/convert elements theo contract. Chỉ clone outer array là shallow.

**Bài 15.** Có thể kiểm thử tính bất biến bằng so `hashCode` duy nhất không?

*Đáp án:* Không. Hash có collisions và không phải mọi immutable class sử dụng hash theo toàn bộ state; cần test observable values và mutation paths.

## 39. Checklist QA trước khi tuyên bố lớp chứa mảng/tập hợp bất biến

- [ ] Đã liệt kê toàn bộ fields và **nested mutable components**?
- [ ] Đã xác định observable state của object?
- [ ] Các instance fields dùng `private final` khi thích hợp?
- [ ] Class có cần `final` để ngăn subclass phá contract không?
- [ ] Constructor đã khởi tạo **đầy đủ và hợp lệ** trước khi trả về?
- [ ] Mọi input arrays đều được copy ở ingress?
- [ ] Mảng nhiều chiều đã copy các inner arrays cần thiết?
- [ ] Object arrays chứa mutable elements đã được deep-snapshot/convert đúng contract?
- [ ] Mutable List/Set/Map inputs được snapshot cấu trúc?
- [ ] Đã phân biệt `List.copyOf` với `Collections.unmodifiableList(source)` view?
- [ ] Nếu dùng view, backing collection có bị mutate từ nơi khác không?
- [ ] Elements/keys/values là immutable hay còn aliases tới mutable objects?
- [ ] Getter không trả mutable array/map/list nội bộ?
- [ ] Nếu getter trả unmodifiable collection, đã thử mutate từ input alias?
- [ ] Nếu getter trả mutable copy, đã thử mutate copy và đọc lại original?
- [ ] Nếu getter trả nested collections, đã thử mutate inner elements?
- [ ] Iterators, list iterators, map entries, subviews có làm lộ khả năng mutate không?
- [ ] Nếu dùng record với array/list component, constructor/accessor có defensive copy?
- [ ] Nếu equality dựa vào contents, equals/hashCode đã được định nghĩa nhất quán?
- [ ] Không để mutable key/element hash thay đổi khi object được dùng trong Set/Map?
- [ ] Constructor có xác định null/blank/invalid-input policy?
- [ ] Mọi đường lỗi constructor được kiểm thử và không trả instance hoàn chỉnh sai invariant?
- [ ] Constructor không để `this` escape sớm?
- [ ] Đã xét concurrent mutation của source khi snapshot?
- [ ] Tests không dựa vào identity của `List.of` hoặc iteration order không được bảo đảm?
- [ ] Có test ingress, egress, nested alias và final observable state?
- [ ] Ví dụ Java 17+ có file/public class đúng, lệnh `javac`/`java`, stdout xác định?

---

**Ghi nhớ cuối bài:** Khi lớp chứa **mảng hoặc tập hợp**, `private final` chỉ bảo vệ việc gán lại **tham chiếu**, không tự làm toàn bộ object graph bất biến. Muốn **kiểm tra** tính bất biến, hãy cố sửa **dữ liệu đầu vào sau constructor**, **giá trị nhận từ getters**, **nested mutable elements** và **backing collections** từ mọi alias đang tồn tại. Với mảng primitive, thường clone ở cả constructor và getter; với mảng nhiều chiều hoặc object arrays, phải snapshot các tầng mutable thích hợp. Với collections, `List.copyOf`/`Set.copyOf`/`Map.copyOf` tạo unmodifiable structures nhưng không đóng băng mutable elements, còn `Collections.unmodifiableList` trên mutable source là **view**, không mặc nhiên là snapshot. Bất biến là **hợp đồng về trạng thái quan sát được**, không phải một modifier đơn lẻ — và bộ kiểm thử đúng phải chứng minh hợp đồng ấy qua cả **ingress, egress và nested aliases**.