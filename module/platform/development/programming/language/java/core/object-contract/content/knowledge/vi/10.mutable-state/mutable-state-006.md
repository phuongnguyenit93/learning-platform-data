# Sao chép phòng vệ để bảo vệ trường mảng hoặc tập hợp trong Java

## 1. Vì sao một trường `private final` vẫn có thể bị sửa?

Sao chép phòng vệ (*defensive copying*) là tạo một bản dữ liệu riêng tại ranh giới giữa đối tượng và mã bên ngoài, để bên ngoài không thể sửa **trạng thái nội bộ** thông qua một tham chiếu được chia sẻ. Kỹ thuật này đặc biệt quan trọng với mảng và các tập hợp có thể thay đổi, vì cả hai đều là đối tượng được truyền và trả về **qua tham chiếu** trong Java.

Xét một lớp giữ dữ liệu đo lường:

```java
// Ví dụ cố ý không an toàn; chưa phải chương trình độc lập.
final class UnsafeMeasurements {
    private final int[] values;

    UnsafeMeasurements(int[] values) {
        this.values = values;
    }

    int[] getValues() {
        return values;
    }
}
```

Gọi `new UnsafeMeasurements(source)` chỉ sao chép **tham chiếu** từ biến `source` sang field `values`; nó không sao chép các phần tử. Bởi vậy:

- Nếu bên gọi sửa `source[0]` sau khi khởi tạo, nội dung `values` bên trong thay đổi theo.
- Nếu bên gọi nhận `getValues()` rồi sửa mảng trả về, nó đang sửa trực tiếp field nội bộ.
- `private` chỉ ngăn truy cập field trực tiếp từ mã khác, còn `final` chỉ cấm **gán lại tham chiếu** `values`; cả hai không cấm thay đổi phần tử của mảng đã tham chiếu.

Với `List`, `Set`, `Map`, cùng vấn đề xảy ra khi constructor giữ nguyên tập hợp đầu vào hoặc getter trả ra collection mutable nội bộ. Hiện tượng nhiều vị trí cùng giữ tham chiếu đến một đối tượng gọi là **aliasing**.

Bài học quan trọng trong chủ đề hợp đồng đối tượng: nếu `equals()` hoặc `hashCode()` dựa vào mảng/collection này, một sửa đổi từ bên ngoài có thể làm hai đối tượng thay đổi quan hệ bằng nhau hoặc khiến khóa đang nằm trong `HashMap`/`HashSet` không còn tra cứu đúng. Defensive copying giúp thiết lập và giữ bất biến (*invariant*) của lớp.

## 2. Hai chiều cần bảo vệ: lúc nhận vào và lúc trả ra

Một lớp thực sự muốn kiểm soát trạng thái phải xem xét **cả đầu vào và đầu ra**:

1. **Copy-in:** sao chép đối tượng mutable được truyền cho constructor hoặc setter, trước khi lưu vào field.
2. **Copy-out:** sao chép đối tượng mutable trước khi trả cho mã bên ngoài bằng getter hoặc phương thức cung cấp dữ liệu.

Nếu chỉ sao chép ở constructor nhưng getter trả mảng gốc bên trong, đối tượng vẫn bị phá từ phía đầu ra. Nếu chỉ sao chép ở getter nhưng constructor giữ nguyên mảng đầu vào, bên gọi vẫn có thể sửa nội bộ bằng tham chiếu đã truyền vào.

Minh họa:

```text
Trường hợp nguy hiểm:
caller.source ───────────┐
                         ├──> cùng mảng mutable <── getter
object.internal ─────────┘

Copy-in + copy-out:
caller.source ──copy──> object.internal ──copy──> caller.snapshot
     ↑                        ↑                           ↑
  mảng riêng              mảng riêng                  mảng riêng
```

Đối với field có kiểu bất biến thật sự, chẳng hạn `String`, không cần sao chép chỉ để chống sửa nội dung. Nhưng một container không cho phép sửa không tự động làm cho **các phần tử được chứa** trở nên bất biến.

## 3. Mảng một chiều: `clone()` hoặc `Arrays.copyOf()`

Với mảng một chiều chứa primitive như `int[]`, cả `clone()` và `Arrays.copyOf(input, input.length)` tạo một mảng **mới** và sao chép các giá trị. Bản sao độc lập với mảng nguồn về khả năng sửa phần tử.

```java
import java.util.Arrays;
import java.util.Objects;

// Mảnh code bên trong lớp đang sở hữu int[].
private final int[] values;

public Example(int[] input) {
    this.values = Objects.requireNonNull(input, "input").clone();
}

public int[] values() {
    return values.clone();
}
```

Đoạn trên chỉ minh họa phương thức và field trong một lớp tên `Example`; muốn biên dịch độc lập cần bao bọc chúng trong khai báo lớp hợp lệ. Với dữ liệu không `null`, cũng có thể dùng `Arrays.copyOf(input, input.length)`; đối với đoạn mảng, có `Arrays.copyOfRange(...)`. Sao chép không có nghĩa là sắp xếp, chuẩn hóa hay lọc; các phần tử được giữ nguyên theo thứ tự.

Lưu ý phạm vi: `clone()` trên **mảng một chiều có phần tử là object mutable** vẫn chỉ tạo bản sao *nông* (*shallow copy*): hai mảng chứa các tham chiếu đến **chính cùng các object phần tử**. Ví dụ, sao chép `StringBuilder[]` tạo mảng vỏ mới, nhưng `StringBuilder` bên trong vẫn bị chia sẻ. Với `String[]`, các phần tử `String` bất biến nên một bản sao nông của mảng thường là đủ.

## 4. Collection: bản sao độc lập và view không sửa được

### 4.1. `List.copyOf`, `Set.copyOf`, `Map.copyOf`

Từ Java 10, `List.copyOf(collection)` tạo một danh sách **không hỗ trợ thao tác sửa** với các phần tử của collection tại thời điểm sao chép. Tương tự có `Set.copyOf` và `Map.copyOf`. Đây là lựa chọn gọn khi dữ liệu phần tử cũng bất biến và bạn muốn API chỉ đọc:

```java
import java.util.List;
import java.util.Objects;

// Mảnh code bên trong một lớp lưu danh sách String.
private final List<String> tags;

public Example(List<String> source) {
    this.tags = List.copyOf(Objects.requireNonNull(source, "source"));
}

public List<String> tags() {
    return tags; // Được vì collection không cho sửa và String là bất biến.
}
```

**Các giới hạn cần biết:**

- `List.copyOf`, `Set.copyOf`, `Map.copyOf` từ chối phần tử `null`; `Map.copyOf` còn từ chối key/value `null`. Tùy lớp mà kiểm tra và thông báo lỗi phù hợp.
- `Set.copyOf` nhận dữ liệu collection và chỉ giữ các phần tử phân biệt; thứ tự duyệt của set tạo ra không được hứa hẹn. `Map.copyOf` cũng không hứa hẹn thứ tự duyệt. Nếu thứ tự có ý nghĩa, cần cách lưu và công bố thứ tự phù hợp.
- Nếu nguồn đã thuộc loại immutable phù hợp, `copyOf` **có thể tái sử dụng** object nguồn; bạn không nên dựa vào việc nó luôn cấp phát một instance mới. Bất biến cần chứng minh nằm ở khả năng sửa thông qua API và tính ổn định của giá trị phần tử.
- `copyOf` sao chép **cấu trúc collection**, nhưng **không tự sao chép sâu các phần tử**. Một `List<StringBuilder>` có thể là danh sách không cho `add`/`set` nhưng các `StringBuilder` bên trong vẫn thay đổi được.

### 4.2. `Collections.unmodifiableList` chưa chắc là snapshot

Một **view không sửa được** vẫn có thể phản ánh thay đổi của collection backing mà nó bọc:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Mảnh code minh họa.
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

Mặc dù `view.add(...)` sẽ ném `UnsupportedOperationException`, dữ liệu hiển thị qua `view` đã thay đổi do bên ngoài sửa `source`. Không nên nhầm **không cho sửa qua view** với **snapshot độc lập**.

Nếu bạn cần giữ giao diện không sửa được, cho phép `null`, hoặc cần bảo toàn thứ tự chèn theo một cấu trúc cụ thể, có thể tạo bản sao trước rồi bọc:

```java
// Mảnh code minh họa.
List<String> snapshot =
    Collections.unmodifiableList(new ArrayList<>(source));
```

`snapshot` không đổi cấu trúc khi `source` thêm/xóa/sửa vị trí về sau, mặc dù nếu phần tử bên trong là object mutable thì cả hai vẫn có thể giữ cùng tham chiếu phần tử. Trên Java 17, khi các phần tử không `null` và không có yêu cầu view đặc thù, `List.copyOf(source)` thường đơn giản hơn.

Tương tự, có thể dùng `Collections.unmodifiableSet(new LinkedHashSet<>(source))` để tạo snapshot set có thứ tự chèn và không cho sửa qua wrapper, hoặc `Collections.unmodifiableMap(new LinkedHashMap<>(source))` khi API cần giữ thứ tự bản đồ. Việc chọn collection cụ thể cần bám yêu cầu dữ liệu.

### 4.3. Getter cho collection

Có hai chiến lược hợp lý:

- **Cung cấp collection bất biến đã lưu:** getter trả trực tiếp `List<String>` được tạo bằng `List.copyOf`, khi phần tử `String` là bất biến. Không cần cấp phát bản sao ở mỗi lượt đọc.
- **Cung cấp snapshot mỗi lần gọi:** nếu lớp chủ động thay đổi collection nội bộ, getter có thể trả `List.copyOf(internal)` hoặc `new ArrayList<>(internal)` bọc unmodifiable, tùy ngữ nghĩa API. Người gọi nhận ảnh chụp cấu trúc tại thời điểm sao chép.

Không coi một getter trả `Collections.unmodifiableList(internalMutableList)` là snapshot: thay đổi về sau của nội bộ vẫn xuất hiện qua view. Nếu đó chính là ngữ nghĩa mong muốn, hãy diễn đạt rõ trong hợp đồng API; nếu cần giá trị bất biến tại thời điểm gọi, phải tạo bản sao.

## 5. Bản sao nông và bản sao sâu

Một bản sao **nông** chỉ sao chép lớp container đầu tiên. Nó đủ nếu container chứa primitive hoặc các đối tượng bất biến. Bản sao **sâu** phải sao chép tiếp những thành phần mutable bên trong đến độ sâu cần thiết để không còn đường sửa ngoài ý muốn.

| Kiểu field | Copy nông thông thường | Có đủ để ngăn thay đổi từ ngoài? |
| --- | --- | --- |
| `int[]` | `array.clone()` | Có, đối với nội dung mảng primitive đó |
| `String[]` | `array.clone()` | Có, vì `String` bất biến |
| `StringBuilder[]` | `array.clone()` | Không, các builder vẫn được chia sẻ |
| `int[][]` | `matrix.clone()` | Không, các mảng hàng `int[]` vẫn được chia sẻ |
| `List<String>` | `List.copyOf(list)` | Có về phần tử String và cấu trúc danh sách |
| `List<MutableItem>` | `List.copyOf(list)` | Không, các `MutableItem` vẫn được chia sẻ |
| `Map<String, MutableValue>` | `Map.copyOf(map)` | Không, các value mutable vẫn có thể bị sửa |

Đối với `int[][]`, cần sao chép **mảng ngoài và từng mảng hàng**; không cần giả định ma trận là hình chữ nhật:

```java
import java.util.Objects;

// Mảnh code minh họa một hàm riêng cho int[][].
static int[][] deepCopy(int[][] source) {
    Objects.requireNonNull(source, "source");
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = Objects.requireNonNull(source[i], "row").clone();
    }
    return result;
}
```

Hàm này cố ý không chấp nhận hàng `null`; có thể giữ `null` nếu hợp đồng dữ liệu cho phép bằng cách xử lý tường minh. Khi field là `List<List<String>>`, một hướng là tạo `List.copyOf` cho từng danh sách con và tiếp tục `List.copyOf` cho danh sách ngoài; do `String` bất biến, kết quả không cho sửa ở cả hai cấp. Với `List<Person>` mà `Person` mutable, phải xác định cách sao chép `Person` hoặc lưu một immutable DTO/snapshot tương ứng; không có phép `deepCopy()` tổng quát nào luôn đúng cho mọi mô hình đối tượng.

## 6. Ví dụ Java 17 chạy được: lỗi aliasing và ba cách khắc phục

Chương trình sau cho thấy:

1. Khóa `UnsafeKey` giữ mảng nguồn, làm hash thay đổi khi bên ngoài sửa mảng.
2. `SafeKey` sao chép mảng ở cả constructor và getter, giữ nguyên ngữ nghĩa của `equals/hashCode`.
3. `Labels` giữ danh sách `String` không sửa được bằng `List.copyOf`.
4. `IntGrid` sao chép sâu ma trận `int[][]` ở cả đầu vào và đầu ra, đồng thời so sánh theo nội dung.

Lưu vào tệp **`DefensiveCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class DefensiveCopyDemo {
    static final class UnsafeKey {
        private final int[] numbers;

        UnsafeKey(int[] numbers) {
            this.numbers = Objects.requireNonNull(numbers);
        }

        String describe() {
            return Arrays.toString(numbers);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof UnsafeKey that)) return false;
            return Arrays.equals(numbers, that.numbers);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class SafeKey {
        private final int[] numbers;

        SafeKey(int[] numbers) {
            this.numbers = Objects.requireNonNull(numbers).clone();
        }

        int[] numbers() {
            return numbers.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof SafeKey that)) return false;
            return Arrays.equals(numbers, that.numbers);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class Labels {
        private final List<String> labels;

        Labels(List<String> input) {
            labels = List.copyOf(Objects.requireNonNull(input));
        }

        List<String> labels() {
            return labels;
        }
    }

    static final class IntGrid {
        private final int[][] cells;

        IntGrid(int[][] input) {
            cells = deepCopy(input);
        }

        int[][] snapshot() {
            return deepCopy(cells);
        }

        private static int[][] deepCopy(int[][] source) {
            Objects.requireNonNull(source);
            int[][] copy = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                copy[i] = Objects.requireNonNull(source[i]).clone();
            }
            return copy;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof IntGrid that)) return false;
            return Arrays.deepEquals(cells, that.cells);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(cells);
        }
    }

    public static void main(String[] args) {
        int[] source = {1, 2};
        UnsafeKey unsafe = new UnsafeKey(source);
        int unsafeHashBefore = unsafe.hashCode();
        source[0] = 9;
        System.out.println("Unsafe values: " + unsafe.describe());
        System.out.println("Unsafe hash changed: "
            + (unsafeHashBefore != unsafe.hashCode()));

        int[] original = {1, 2};
        SafeKey safe = new SafeKey(original);
        int safeHashBefore = safe.hashCode();
        Set<SafeKey> set = new HashSet<>();
        set.add(safe);
        original[0] = 9;
        int[] returned = safe.numbers();
        returned[1] = 99;
        System.out.println("Safe values: " + Arrays.toString(safe.numbers()));
        System.out.println("Safe hash stable: "
            + (safeHashBefore == safe.hashCode()));
        System.out.println("Safe equal to new key: "
            + safe.equals(new SafeKey(new int[] {1, 2})));
        System.out.println("Safe HashSet lookup: "
            + set.contains(new SafeKey(new int[] {1, 2})));

        List<String> input = new ArrayList<>(List.of("red", "blue"));
        Labels labels = new Labels(input);
        input.add("green");
        System.out.println("Labels snapshot: " + labels.labels());
        try {
            labels.labels().add("black");
        } catch (UnsupportedOperationException e) {
            System.out.println("Labels cannot be edited: true");
        }

        int[][] matrix = {{1, 2}, {3, 4}};
        IntGrid grid = new IntGrid(matrix);
        matrix[0][0] = 99;
        int[][] leaked = grid.snapshot();
        leaked[1][1] = 88;
        System.out.println("Grid row 0: "
            + Arrays.toString(grid.snapshot()[0]));
        System.out.println("Grid row 1: "
            + Arrays.toString(grid.snapshot()[1]));
        System.out.println("Grid equals same contents: "
            + grid.equals(new IntGrid(new int[][] {{1, 2}, {3, 4}})));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp với **JDK 17+**:

```bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
```

Kết quả xác định:

```text
Unsafe values: [9, 2]
Unsafe hash changed: true
Safe values: [1, 2]
Safe hash stable: true
Safe equal to new key: true
Safe HashSet lookup: true
Labels snapshot: [red, blue]
Labels cannot be edited: true
Grid row 0: [1, 2]
Grid row 1: [3, 4]
Grid equals same contents: true
```

**Vì sao có những kết quả này?**

- `UnsafeKey` giữ tham chiếu trực tiếp tới `source`; đổi `source[0]` cũng đổi nội dung mà `equals()` và `hashCode()` nhìn thấy. Hash của mảng `{1, 2}` và `{9, 2}` thực sự khác nhau theo `Arrays.hashCode(int[])`. Nếu một khóa như vậy được thêm vào `HashSet` hoặc `HashMap` rồi bị sửa, thao tác tìm kiếm có thể thất bại do hash đã đổi; không cần phụ thuộc chi tiết bucket để chứng minh rủi ro.
- `SafeKey` sao chép lúc nhận đầu vào **và** lúc xuất mảng. Các thay đổi `original[0] = 9` và `returned[1] = 99` chỉ ảnh hưởng hai mảng của bên gọi, không chạm mảng trong `safe`. Do đó hash ổn định; một `SafeKey` mới cùng phần tử được tìm thấy trong `HashSet`.
- `Labels` chụp cấu trúc danh sách tại thời điểm constructor chạy. Thêm `"green"` vào danh sách nguồn không sửa bản đã lưu; getter trả collection không hỗ trợ `add`. Các phần tử ở đây là `String` bất biến nên không có aliasing mutable ở cấp phần tử.
- `IntGrid` chụp cả mảng ngoài và từng hàng. Thay đổi mảng nguồn hay ma trận trả về đều không đổi field; `Arrays.deepEquals` và `Arrays.deepHashCode` phù hợp để so/hash nội dung mảng lồng nhau.

## 7. Defensive copying gắn với `equals()` và `hashCode()` thế nào?

Nếu đối tượng là **value object** được định nghĩa bằng nội dung mảng hay tập hợp, nên giữ dữ liệu đó ổn định để phép so sánh có ý nghĩa lâu dài.

Với mảng:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof SafeKey that)) return false;
    return Arrays.equals(numbers, that.numbers);
}

@Override
public int hashCode() {
    return Arrays.hashCode(numbers);
}
```

Đây là hai phương thức trong `SafeKey` ở ví dụ trước, không phải chương trình độc lập.

Với ma trận `int[][]`, `Arrays.deepEquals` phải đi cùng `Arrays.deepHashCode` nếu equality là theo nội dung ở các hàng. Nếu chỉ dùng `Objects.equals(array1, array2)` thì thông thường bạn đang so **tham chiếu mảng**, không phải phần tử. Nếu chỉ dùng `Arrays.equals` cho `int[][]` thì các mảng hàng vẫn được so theo tham chiếu.

Với `List<String>`, `List.equals` và `List.hashCode` đã có ngữ nghĩa nội dung và thứ tự được định nghĩa nhất quán. Đừng viết hash thủ công dựa trên danh sách rồi cho phép người gọi sửa list hoặc sửa object phần tử liên quan đến equality.

**Một điểm then chốt:** defensive copy bảo vệ khỏi những thay đổi **qua alias được phát ra hoặc nhận vào**. Nó không tự động biến tất cả đối tượng thành bất biến nếu chính class vẫn cung cấp setter sửa những trường tham gia equality/hash. Nếu cần dùng làm khóa hash ổn định, cần thiết kế các thành phần định danh bất biến hoặc tránh thay đổi chúng trong thời gian object nằm trong collection băm.

## 8. Record, constructor và các đối tượng lồng nhau

Record Java không tự động sao chép array/collection. Component field của record là `private final`, nhưng dữ liệu được tham chiếu có thể mutable. Có thể dùng **compact canonical constructor** để copy-in và ghi đè accessor để copy-out khi component là mảng:

```java
import java.util.Arrays;
import java.util.Objects;

// Ví dụ minh họa record độc lập nhưng không có main.
record BytePacket(byte[] payload) {
    public BytePacket {
        payload = Objects.requireNonNull(payload).clone();
    }

    @Override
    public byte[] payload() {
        return payload.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BytePacket that
            && Arrays.equals(payload, that.payload);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(payload);
    }
}
```

**Vì sao còn phải ghi đè `equals/hashCode`?** Equality/hash mặc định sinh cho record với component kiểu mảng **không** tự so nội dung mảng sâu; hai record chứa hai mảng khác instance nhưng cùng byte có thể bị coi khác nhau theo mặc định. Nếu mục tiêu là so payload byte theo nội dung, phải dùng hai phương thức mảng tương ứng như trên.

Nếu record chứa `List<String>`, có thể làm:

```java
// Minh họa record khác, Java 17.
record TagSnapshot(List<String> tags) {
    public TagSnapshot {
        tags = List.copyOf(tags);
    }
}
```

Khi dữ liệu là `String` bất biến, getter `tags()` mặc định có thể trả trực tiếp immutable list. Nếu record giữ `List<MutableItem>`, cần sao chép/phong tỏa từng phần tử theo quy tắc của lớp; chỉ `List.copyOf` là chưa đủ.

## 9. Những sai sót hay gặp

| Sai sót | Vì sao nguy hiểm | Khắc phục |
| --- | --- | --- |
| Constructor lưu thẳng mảng/`ArrayList` đầu vào | Bên gọi giữ alias sửa nội bộ bất cứ lúc nào | Copy-in trước khi lưu |
| Constructor đã copy, getter lại trả field mảng trực tiếp | Bên gọi sửa nội bộ qua getter | Copy-out mỗi lượt hoặc API chỉ đọc an toàn |
| Chỉ dùng `Collections.unmodifiableList(source)` | Đây là view; thay đổi của `source` vẫn hiển thị | Tạo snapshot trước hoặc `List.copyOf` |
| Dùng `List.copyOf` cho phần tử mutable và tưởng đã deep copy | Phần tử vẫn được chia sẻ | Sao chép phần tử, dùng value bất biến hoặc DTO |
| Dùng `matrix.clone()` cho `int[][]` | Các hàng `int[]` vẫn alias | Clone từng hàng |
| Dùng `Arrays.asList(array)` rồi nghĩ đã tách khỏi mảng | Danh sách có kích thước cố định vẫn được **back bởi mảng gốc**; `set` và sửa mảng ảnh hưởng lẫn nhau | Dùng snapshot phù hợp như `List.copyOf(Arrays.asList(array))` khi phần tử phù hợp |
| Giữ `final List<MutableItem>` | `final` không bất biến hóa list hoặc phần tử | Chọn immutable representation và defensive copy |
| Expose `Map<K, MutableValue>` dù `Map.copyOf` | Các value vẫn có thể đổi | Sao chép/đóng băng value và xử lý nested objects |
| Copy-in nhưng cho setter sửa khóa equality | Hash vẫn đổi do chính class | Thiết kế khóa ổn định hoặc giới hạn vòng đời sử dụng |
| Dùng `List.copyOf` khi dữ liệu hợp lệ có `null` | Ném `NullPointerException` | Định nghĩa null policy và chọn cách copy phù hợp |
| Sao chép đối tượng mutable mà không có snapshot nhất quán giữa các thread | Có thể đọc dữ liệu hỗn hợp khi nguồn đang bị sửa | Đồng bộ/đọc dưới lock hoặc trao đổi dữ liệu bất biến |

## 10. Điều gì không được tự động đảm bảo bởi bản sao?

### 10.1. Copy không đồng nghĩa với hoàn toàn immutable

Một class có thể tạo bản sao mảng ở constructor/getter, nhưng vẫn có một phương thức nội bộ `updateValue(i, v)` thay đổi mảng; khi đó object **vẫn mutable**, chỉ là không bị thay đổi qua alias từ bên ngoài. API cần nêu rõ liệu đối tượng là snapshot cố định hay là đối tượng mutable có kiểm soát.

### 10.2. Deep copy phải có nghĩa cụ thể

Với đồ thị đối tượng phức tạp, vòng tham chiếu, object liên kết hoặc tài nguyên như file/socket, “copy sâu tất cả” không phải luôn khả thi hoặc mong muốn. Chọn mức bảo vệ tại ranh giới dữ liệu: trường nào phải bất biến, phần tử nào được chia sẻ an toàn, phần tử nào cần snapshot. Khi cần, dùng constructor copy hoặc phương thức tạo snapshot do chính loại phần tử định nghĩa.

### 10.3. Copy khi bị ghi đồng thời không tạo snapshot nguyên tử

Ví dụ, một thread đang thêm/xóa phần tử vào `ArrayList` trong lúc thread khác gọi `List.copyOf(source)`: cách sao chép không tự mang lại sự đồng bộ giữa threads. Tương tự, copy các phần tử mảng khi thread khác sửa có thể thấy các giá trị ở những thời điểm khác nhau. Nếu cần snapshot nhất quán trong môi trường đồng thời, cả phía ghi và phía copy cần tuân thủ một giao thức đồng bộ phù hợp, hoặc chuyển sang dữ liệu bất biến/cơ chế snapshot được thiết kế cho concurrency.

### 10.4. Sao chép có chi phí

Copy-in và copy-out tiêu tốn bộ nhớ và thời gian tỷ lệ với lượng dữ liệu được sao chép. Với getter được gọi liên tục trên mảng lớn, copy-out có thể đắt. Có thể thiết kế API truy vấn cụ thể như `size()`, `get(index)` trả primitive/bất biến, trả iterator/snapshot có kiểm soát, hoặc lưu sẵn immutable collection và trả trực tiếp. Tối ưu khi vẫn giữ đúng cam kết về tính bất biến và bảo vệ trạng thái.

## 11. Checklist khi review mã nguồn

1. Class có field là mảng, collection hoặc object chứa trạng thái mutable không?
2. Constructor, builder, factory và setter có giữ lại tham chiếu mutable mà bên ngoài tiếp tục sở hữu không?
3. Getter, accessor, method callback hoặc phương thức trả phần tử có tiết lộ tham chiếu mutable nội bộ không?
4. Copy hiện tại là shallow hay deep? Các phần tử và collection lồng nhau có còn alias không?
5. Chọn immutable snapshot hay unmodifiable view? Nguồn được sửa về sau có làm dữ liệu trả ra thay đổi không?
6. Quy tắc `null`, duplicate, thứ tự và canonicalization của collection có được giữ đúng không?
7. `equals/hashCode` có dùng trạng thái mutable bị lộ ra ngoài không? Hash có thể đổi sau khi dùng làm khóa `HashMap/HashSet` không?
8. Có trường hợp concurrent writer và copier không? Snapshot có cần nhất quán nguyên tử không?
9. Bài kiểm tra đã thử **sửa đầu vào sau constructor** và **sửa kết quả getter** ở mọi cấp nested chưa?

Một phép thử hiệu quả là tạo object từ dữ liệu mutable, ghi nhận giá trị, sửa nguồn, đọc lại; sau đó sửa cả dữ liệu mà accessor trả về và kiểm tra object lần nữa. Đối với khóa hash, thêm object vào `HashSet`, tác động qua các alias có thể tồn tại, rồi kiểm tra equality/hash và tra cứu. Đừng chỉ thử trường hợp không có sửa đổi.

## 12. Tự kiểm tra

**Câu 1.** `private final int[] scores` có khiến mọi phần tử trong `scores` bất biến không?

**Đáp án:** Không. `final` ngăn gán lại field tham chiếu, nhưng `scores[0] = 123` vẫn có thể xảy ra nếu có quyền truy cập mảng.

**Câu 2.** Nếu constructor đã gọi `input.clone()` nhưng getter trả `internalArray` trực tiếp, lớp đã được bảo vệ hoàn toàn chưa?

**Đáp án:** Chưa. Bên gọi vẫn có thể sửa mảng nhận từ getter. Cần trả bản sao hoặc thiết kế API đọc không tiết lộ mutable reference.

**Câu 3.** `Collections.unmodifiableList(input)` và `List.copyOf(input)` có giống nhau về việc bên ngoài sửa `input` sau này không?

**Đáp án:** Không. `unmodifiableList` chỉ tạo view không cho sửa qua view nhưng phản ánh thay đổi từ backing list; `List.copyOf` chụp cấu trúc và không cho sửa cấu trúc bản snapshot. Cả hai đều không tự sao chép sâu object phần tử.

**Câu 4.** Sao chép `int[][] original` bằng `original.clone()` đã đủ để các phần tử `original[0][0]` độc lập chưa?

**Đáp án:** Chưa. Các hàng vẫn là mảng dùng chung; cần sao chép từng mảng con.

**Câu 5.** `List.copyOf(List<StringBuilder>)` ngăn được việc người giữ tham chiếu đến một `StringBuilder` gọi `append` không?

**Đáp án:** Không. `List.copyOf` chỉ ngăn sửa cấu trúc qua API list; `StringBuilder` vẫn là object mutable được chia sẻ.

**Câu 6.** Có thể trả trực tiếp một `List<String>` đã lưu bằng `List.copyOf` từ getter mà vẫn bảo vệ nội bộ không?

**Đáp án:** Có, khi chính list không hỗ trợ sửa và các phần tử `String` bất biến; việc gọi `add/set/remove` qua getter không sửa được trạng thái của lớp.

**Câu 7.** Một value object có `hashCode()` dựa vào mảng mutable; bạn đã copy-in và copy-out nhưng bản thân lớp còn method sửa mảng nội bộ. Có thể dùng làm khóa `HashMap` không cần cân nhắc nữa không?

**Đáp án:** Chưa. Defensive copy ngăn aliasing ngoài ý muốn, không ngăn các phương thức của class làm thay đổi thành phần equality/hash. Cần giữ thành phần hash ổn định trong lúc làm khóa hoặc chọn thiết kế khác.

---

**Ghi nhớ:** Với mảng và collection mutable, hãy xác định **ai sở hữu dữ liệu tại mỗi ranh giới API**. Thường cần copy-in khi nhận, copy-out khi công bố; chọn snapshot thay vì view nếu muốn tách khỏi thay đổi tương lai. Sao chép nông chỉ đủ khi phần tử bất biến; dữ liệu lồng nhau cần chính sách sao chép sâu phù hợp. Bảo vệ trạng thái giúp `equals()` và `hashCode()` nhất quán khi chúng dựa trên các giá trị đó.