# Bất biến sao chép qua accessor và hàm khởi tạo chuẩn của `record`

## 1. Vấn đề: `record` có trường `final` nhưng thành phần vẫn có thể thay đổi

`record` (Java 16+, ổn định trong Java 17) là kiểu dữ liệu nhằm mô tả **bộ giá trị được xác định bởi các thành phần (record components)**. Khi khai báo:

```java
record Report(int id, int[] scores) {}
```

trình biên dịch cung cấp các thành phần cơ bản như trường riêng `private final` cho từng component, constructor chuẩn (canonical constructor), accessor `id()`/`scores()`, cùng `equals`, `hashCode` và `toString`. Nhưng `final` **chỉ cố định tham chiếu trong trường**; nó không khiến đối tượng mà trường trỏ tới trở nên bất biến.

Vì vậy:

- Một đối tượng gọi `new Report(1, array)` mặc định **giữ chính tham chiếu mảng đầu vào**.
- Gọi `report.scores()` mặc định **trả lại tham chiếu mảng nội bộ ấy**.
- Người bên ngoài có thể sửa mảng qua biến đầu vào hoặc qua accessor, khiến trạng thái quan sát được của `report` thay đổi sau khi tạo.

Đây là **bất biến nông** (shallow immutability): tham chiếu component cố định nhưng nội dung có thể thay đổi. Muốn xây dựng record có **giá trị ổn định**, cần bảo vệ cả hai đường truy cập:

1. **Đường vào**: trong constructor chuẩn, lưu một **bản sao phòng vệ** (defensive copy) hoặc một biểu diễn bất biến thay cho dữ liệu mutable do bên ngoài truyền tới.
2. **Đường ra**: accessor không trả trực tiếp một đối tượng nội bộ mutable; trả bản sao phù hợp hoặc một giao diện bất biến an toàn.

Bài học này tập trung vào hai điểm trên, cách viết đúng trong canonical constructor của Java record, và tác động lên hợp đồng `equals`/`hashCode`.

## 2. Canonical constructor và accessor của record hoạt động ra sao?

Với:

```java
record OrderLine(String sku, int[] quantities) {}
```

các component được biểu diễn bằng trường riêng, `final`. Canonical constructor nhận tham số đúng thứ tự/kiểu của các component, và accessor công khai `sku()`, `quantities()` có kiểu trả về tương ứng. Trong khai báo cơ bản, việc khởi tạo `quantities` tương đương lưu tham chiếu truyền vào; accessor trả lại tham chiếu đó. Không có cơ chế tự sao chép phần tử mảng.

**Canonical constructor có hai dạng chính** cần phân biệt:

### Constructor chuẩn đầy đủ (explicit canonical constructor)

Khi cần kiểm soát mọi phép gán, viết đầy đủ danh sách tham số:

```java
import java.util.Arrays;
import java.util.Objects;

record Scores(int[] values) {
    public Scores(int[] values) {
        Objects.requireNonNull(values, "values");
        this.values = Arrays.copyOf(values, values.length);
    }

    public int[] values() {
        return values.clone();
    }
}
```

Đoạn này là một record hợp lệ (đặt trong tệp `Scores.java` cùng import); nó thể hiện cách sao chép hai hướng. Trong constructor chuẩn đầy đủ, phải khởi tạo các trường component theo quy tắc definite assignment, và không bỏ sót component nào. Ở đây `this.values` nhận **mảng mới**, không nhận mảng do caller sở hữu.

### Constructor chuẩn rút gọn (compact canonical constructor)

Java cho phép bỏ phần danh sách tham số; tham số component được khai báo ngầm và **các trường component được gán tự động từ giá trị tham số khi phần thân compact constructor kết thúc bình thường**:

```java
import java.util.Objects;

record Scores(int[] values) {
    public Scores {
        Objects.requireNonNull(values, "values");
        values = values.clone(); // Gán lại tham số của compact constructor.
    }

    public int[] values() {
        return values.clone();
    }
}
```

Hai ví dụ cho cùng chính sách bảo vệ: **sao chép khi nhận** và **sao chép khi trả**. Trong compact constructor, dòng `values = values.clone()` cập nhật **tham số cục bộ**; phần gán ngầm cuối constructor đưa tham số mới vào trường component. Không viết `this.values = ...` trong phần thân compact constructor: việc gán trường component trực tiếp ở đây không hợp lệ; cơ chế gán ngầm chịu trách nhiệm cho nó.

Lưu ý đây là **hai cách triển khai thay thế của cùng record `Scores`**. Nếu thử biên dịch, chọn một đoạn làm nội dung của `Scores.java`, không đặt cả hai định nghĩa record cùng tên trong một tệp.

## 3. Hai hướng “rò rỉ” dữ liệu mutable

Giả sử record chưa có biện pháp bảo vệ:

```java
record UnsafeScores(int[] values) {}
```

**Rò rỉ từ constructor (đường vào):**

```java
int[] source = {10, 20};
UnsafeScores report = new UnsafeScores(source);
source[0] = 99;

// report.values()[0] lúc này là 99.
```

Caller nắm `source` và record cũng dùng chính mảng đó. Việc sửa đầu vào sau khi tạo record làm thay đổi trạng thái được record biểu diễn.

**Rò rỉ từ accessor (đường ra):**

```java
UnsafeScores report = new UnsafeScores(new int[] {10, 20});
int[] leaked = report.values();
leaked[1] = 88;

// report.values()[1] lúc này là 88.
```

Mỗi đoạn trên là **ví dụ minh họa**, không phải chương trình độc lập. Dù component là `private final`, dữ liệu vẫn mutable qua đường tham chiếu.

| Record làm gì? | Sau đó ai có thể sửa dữ liệu nội bộ? | Kết quả |
| --- | --- | --- |
| Không sao chép ở constructor, không bảo vệ accessor | Cả caller giữ đầu vào và caller nhận từ accessor | Rò rỉ cả hai hướng. |
| Sao chép ở constructor nhưng trả trực tiếp từ accessor | Caller lấy mảng từ accessor | Vẫn không bất biến. |
| Giữ trực tiếp tham chiếu đầu vào nhưng sao chép ở accessor | Caller còn giữ mảng đầu vào | Vẫn không bất biến. |
| Sao chép ở constructor và sao chép ở accessor | Caller không thể sửa trực tiếp các phần tử mảng nội bộ qua hai đường này | Đủ cho mảng **một chiều chứa giá trị nguyên thủy**, nếu lớp không còn lộ tham chiếu mutable qua đường khác. |

**Chỉ một hướng sao chép là chưa đủ.** Cần kiểm tra toàn bộ điểm nhận và xuất dữ liệu, kể cả phương thức được tự viết thêm trong record.

## 4. Chọn phương pháp sao chép theo kiểu component

Không có một hàm sao chép chung đúng cho mọi loại dữ liệu.

| Component | Giải pháp thông thường | Giới hạn cần hiểu |
| --- | --- | --- |
| `int[]`, `byte[]`, `char[]` | `clone()` hoặc `Arrays.copyOf` khi nhập và xuất | Mảng một chiều chứa các giá trị nguyên thủy; một lần copy là đủ để tách các phần tử. |
| `String[]` | Sao chép mảng khi nhập/xuất; `String` bất biến | Mảng ngoài mới nhưng các chuỗi được chia sẻ an toàn do bản thân `String` bất biến. |
| `Object[]` chứa đối tượng mutable | Sao chép mảng **và** sao chép/đóng băng các phần tử theo chính sách | `clone()` chỉ sao chép mảng ngoài; phần tử vẫn là cùng tham chiếu. |
| `int[][]` hoặc mảng nhiều chiều | Tạo mảng ngoài và sao chép **từng mảng con** | `matrix.clone()` chỉ nông; cần lặp từng hàng hoặc xử lý cấu trúc lồng sâu hơn. |
| `List<String>` | `List.copyOf(input)` trong constructor; accessor có thể trả list này | Tập phần tử bất biến (`String`) và list không cho sửa cấu trúc. |
| `List<MutableItem>` | Tạo bản sao bất biến **của từng item** rồi `List.copyOf` | `List.copyOf` không tự sao chép sâu phần tử. |
| `Map<K, V>`, `Set<E>` | `Map.copyOf`, `Set.copyOf` nếu phù hợp | Đây là sao chép cấu trúc bất biến ở cấp collection, không đảm bảo các khóa/giá trị là bất biến sâu. |
| `String`, `Integer`, `LocalDate` hoặc value object thật sự bất biến | Có thể giữ trực tiếp | Không cần sao chép khi đối tượng thành phần vốn bất biến và đáp ứng ngữ nghĩa muốn có. |

Khi dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf`, cần hiểu điều kiện của API, gồm việc không chấp nhận phần tử `null` (`Map.copyOf` cũng không nhận khóa/giá trị `null`). Quy tắc này có thể là ưu điểm về tính nhất quán, nhưng nếu nghiệp vụ cho phép `null` thì phải chọn biểu diễn hoặc chính sách kiểm tra phù hợp.

`List.copyOf` trả về **list không thể sửa cấu trúc thông qua API list**. Không nhầm nó với `Collections.unmodifiableList(input)`: một unmodifiable **view** có thể vẫn phản chiếu các thay đổi được thực hiện thông qua chính `input` gốc. Nếu cần ảnh chụp tách khỏi nguồn, dùng bản sao phù hợp, chẳng hạn `List.copyOf(input)`.

## 5. Ví dụ Java 17+ chạy được: constructor, accessor và `equals`

Chương trình sau minh họa bốn trường hợp:

1. `UnsafeNumbers` giữ và lộ mảng trực tiếp, nên bị sửa qua cả hai hướng.
2. `ImmutableTags` tạo bản snapshot bằng `List.copyOf`. Vì phần tử là `String` bất biến, accessor mặc định có thể trả list đó an toàn.
3. `NumberSnapshot` sao chép mảng cả khi nhập và khi xuất, đồng thời **ghi đè `equals`/`hashCode` theo nội dung** để phù hợp ngữ nghĩa value object.
4. `ShallowBox` dùng `List.copyOf` nhưng vẫn chứa phần tử mutable: sửa phần tử làm thay đổi trạng thái quan sát được.

Lưu vào tệp `RecordDefensiveCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public class RecordDefensiveCopyDemo {
    record UnsafeNumbers(int[] numbers) {}

    record ImmutableTags(List<String> tags) {
        public ImmutableTags {
            Objects.requireNonNull(tags, "tags");
            tags = List.copyOf(tags);
        }
    }

    record NumberSnapshot(int[] numbers) {
        public NumberSnapshot {
            Objects.requireNonNull(numbers, "numbers");
            numbers = numbers.clone();
        }

        // Accessor tường minh: trả mảng mới mỗi lần gọi.
        public int[] numbers() {
            return numbers.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof NumberSnapshot that
                        && Arrays.equals(numbers, that.numbers));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class MutableCell {
        int value;

        MutableCell(int value) {
            this.value = value;
        }
    }

    record ShallowBox(List<MutableCell> cells) {
        public ShallowBox {
            cells = List.copyOf(cells);
        }
    }

    public static void main(String[] args) {
        int[] unsafeSource = {1, 2};
        UnsafeNumbers unsafe = new UnsafeNumbers(unsafeSource);
        unsafeSource[0] = 99;
        System.out.println("unsafe input leak: "
                + Arrays.toString(unsafe.numbers()));
        unsafe.numbers()[1] = 88;
        System.out.println("unsafe accessor leak: "
                + Arrays.toString(unsafe.numbers()));

        List<String> sourceTags =
                new ArrayList<>(List.of("java"));
        ImmutableTags tags = new ImmutableTags(sourceTags);
        sourceTags.add("spring");
        System.out.println("tags after source edit: " + tags.tags());
        try {
            tags.tags().add("kotlin");
        } catch (UnsupportedOperationException exception) {
            System.out.println("tags accessor: unmodifiable");
        }

        int[] source = {10, 20};
        NumberSnapshot safe = new NumberSnapshot(source);
        source[0] = 999;
        System.out.println("safe after input edit: "
                + Arrays.toString(safe.numbers()));

        int[] returned = safe.numbers();
        returned[1] = 777;
        System.out.println("safe after accessor edit: "
                + Arrays.toString(safe.numbers()));

        NumberSnapshot equivalent =
                new NumberSnapshot(new int[] {10, 20});
        System.out.println("snapshot equals: "
                + safe.equals(equivalent));
        System.out.println("snapshot hash equal: "
                + (safe.hashCode() == equivalent.hashCode()));

        Set<NumberSnapshot> set = new HashSet<>();
        set.add(safe);
        System.out.println("set contains equivalent: "
                + set.contains(equivalent));

        UnsafeNumbers raw1 = new UnsafeNumbers(new int[] {10, 20});
        UnsafeNumbers raw2 = new UnsafeNumbers(new int[] {10, 20});
        System.out.println("default array component equals: "
                + raw1.equals(raw2));

        MutableCell cell = new MutableCell(7);
        ShallowBox box =
                new ShallowBox(new ArrayList<>(List.of(cell)));
        cell.value = 8;
        System.out.println("shallow element edit: "
                + box.cells().get(0).value);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RecordDefensiveCopyDemo.java
java RecordDefensiveCopyDemo
```

Kết quả dự kiến chính xác:

```text
unsafe input leak: [99, 2]
unsafe accessor leak: [99, 88]
tags after source edit: [java]
tags accessor: unmodifiable
safe after input edit: [10, 20]
safe after accessor edit: [10, 20]
snapshot equals: true
snapshot hash equal: true
set contains equivalent: true
default array component equals: false
shallow element edit: 8
```

### Đọc kết quả theo từng lớp

**`UnsafeNumbers`:** constructor mặc định lưu `unsafeSource`; sửa `unsafeSource[0]` được phản ánh trong record. Accessor mặc định trả đúng mảng nội bộ, cho phép sửa thêm phần tử thứ hai. Đây là ví dụ không có defensive copy.

**`ImmutableTags`:** constructor chuẩn rút gọn chuyển danh sách thành `List.copyOf(tags)`, rồi Java gán danh sách mới (hoặc một biểu diễn bất biến tương đương) vào trường component khi kết thúc constructor. Sửa `sourceTags` sau đó không ảnh hưởng `tags.tags()`. Accessor mặc định trả list không cho thêm/xóa/phần tử. Vì `String` bất biến, không có lỗ hổng sửa phần tử ở đây.

**`NumberSnapshot`:** constructor nhận một bản sao `int[]`; accessor mỗi lần lại tạo mảng mới. Sửa mảng đầu vào lẫn mảng lấy từ accessor không tác động tới nội bộ. `equals` và `hashCode` đều dựa trên các giá trị phần tử, nên hai snapshot độc lập có cùng nội dung bằng nhau và tra cứu chính xác trong `HashSet`.

**`UnsafeNumbers` theo `equals` sinh tự động:** hai record có mảng con riêng nhưng cùng `{10,20}` không bằng nhau. Đây không phải lỗi riêng của record; `int[].equals` vốn kiểm tra danh tính. `record` sinh `equals` dựa theo component, và với component là mảng, phép so sánh đó phản ánh danh tính mảng, không so từng phần tử.

**`ShallowBox`:** `List.copyOf` đóng băng **cấu trúc list**, nhưng mỗi phần tử vẫn là `MutableCell`. Sửa `cell.value` khiến accessor quan sát được giá trị `8`. Điều này minh họa rằng **collection unmodifiable không đồng nghĩa deep immutability**.

## 6. Bẫy quan trọng: defensive copy và `equals`/`hashCode` sinh tự động của record

Record thông thường cung cấp `equals` và `hashCode` từ các component. Đối với component tham chiếu, quy tắc bằng nhau dùng ngữ nghĩa so sánh component phù hợp; với mảng, các phương thức mặc định của mảng là **theo danh tính**.

Xét record sau:

```java
import java.util.Objects;

record DefensiveButIdentity(int[] values) {
    public DefensiveButIdentity {
        Objects.requireNonNull(values, "values");
        values = values.clone();
    }

    public int[] values() {
        return values.clone();
    }

    // equals() và hashCode() được Java tự sinh.
}
```

Record này đã bảo vệ mảng nội bộ hai hướng, nhưng hai instance tạo từ những mảng cùng nội dung vẫn **không bằng nhau** theo `equals` sinh tự động vì chúng giữ hai mảng component khác nhau. Nghiêm trọng hơn, một bất biến thiết kế quan trọng của record là bản sao được tạo bằng cách truyền lại kết quả accessor của mọi component thường phải tương đương với record gốc về `equals` (copy invariant). Trong trường hợp mảng, accessor tạo mảng mới khiến record mới dùng một tham chiếu mảng khác; `equals` tự sinh không coi hai record đó bằng nhau.

Ví dụ minh họa:

```java
DefensiveButIdentity a =
        new DefensiveButIdentity(new int[] {1, 2});
DefensiveButIdentity b =
        new DefensiveButIdentity(a.values());

// a.equals(b) trả về false theo equals() sinh tự động.
```

**Vì thế, nếu record có component mảng và định dùng như một giá trị bất biến theo nội dung, chỉ viết defensive copy chưa đủ.** Cần lựa chọn ngữ nghĩa đúng:

- **Muốn bằng nhau theo nội dung:** như `NumberSnapshot`, tự viết `equals` dùng `Arrays.equals`, tự viết `hashCode` dùng `Arrays.hashCode`. Với mảng lồng thông thường, dùng cặp `Arrays.deepEquals`/`Arrays.deepHashCode` và bảo vệ tính bất biến của mảng lồng.
- **Muốn dùng so sánh sinh tự động:** chọn kiểu component bản thân đã có ngữ nghĩa bằng nhau theo giá trị và có thể bất biến, ví dụ `List<Integer>` đã sao chép bất biến hoặc một value object được thiết kế phù hợp. Khi đó record có thể dựa vào `equals`/`hashCode` sinh tự động.
- **Muốn thật sự đại diện cho danh tính của một mảng cụ thể:** cần cân nhắc liệu sao chép mảng có trái với chính sách danh tính ấy không; record value object có thể không phải mô hình hợp lý nhất cho nhu cầu này.

Đừng “sửa” bằng cách so sánh `Arrays.hashCode(values)` để suy ra hai mảng có nội dung bằng nhau. Hash có thể va chạm. `equals` xác nhận bằng phần tử; `hashCode` chỉ hỗ trợ định hướng tìm kiếm.

## 7. Cách dùng `List.copyOf` và accessor mặc định cho collection

Khi component là collection **đã bất biến và phần tử cũng bất biến**, không nhất thiết trả một bản sao collection ở mỗi lần gọi accessor. Một record như sau thường đủ:

```java
import java.util.List;
import java.util.Objects;

record Permissions(List<String> names) {
    public Permissions {
        Objects.requireNonNull(names, "names");
        names = List.copyOf(names);
    }
}
```

Sau khi constructor kết thúc, trường `names` giữ một danh sách unmodifiable không bị thay đổi bởi thao tác thêm/xóa trên danh sách nguồn. `String` là immutable nên nội dung cũng ổn định. Accessor sinh tự động `names()` có thể trả chính danh sách đó mà không tạo lỗ hổng mutate thông qua API danh sách.

Lý do phải phân biệt:

- `Collections.unmodifiableList(source)` tạo **view không cho sửa qua view**, nhưng `source.add(...)` bên ngoài vẫn có thể khiến nội dung quan sát qua view thay đổi.
- `List.copyOf(source)` cung cấp một danh sách unmodifiable chứa snapshot của các phần tử tại thời điểm sao chép (hoặc có thể tái sử dụng list đã bất biến), không bị thay đổi bởi các thao tác thêm/xóa trên `source` sau đó.
- Cả hai đều **không sao chép sâu** các đối tượng phần tử mutable. Đối với `List<MutableAddress>`, phải copy/chuyển mỗi địa chỉ thành value object bất biến trước khi dùng `List.copyOf`.
- `List.copyOf` không bảo đảm bảo toàn **danh tính tham chiếu** của đối tượng list; code nên dựa vào giá trị và hợp đồng danh sách.
- Với record có list bất biến, `equals`/`hashCode` tự sinh dựa trên `List.equals`/`List.hashCode` vốn so theo phần tử, nếu thành phần phần tử có ngữ nghĩa hợp lệ.

Một chính sách thiết kế hữu ích: **sao chép một lần ở constructor, trả trực tiếp qua accessor khi đối tượng đã thực sự bất biến**; nếu component là mutable array thì **sao chép cả lúc nhập lẫn lúc xuất**.

## 8. Sao chép sâu: mảng nhiều chiều và phần tử mutable

### 8.1. Mảng hai chiều

`int[][]` thực chất là mảng chứa tham chiếu tới các `int[]`. Do đó `input.clone()` chỉ sao chép mảng ngoài. Nếu muốn snapshot độc lập, phải sao chép **từng hàng**. Ví dụ đoạn logic cho mảng không có hàng `null`:

```java
private static int[][] copyMatrix(int[][] source) {
    Objects.requireNonNull(source, "source");
    int[][] copy = new int[source.length][];
    for (int row = 0; row < source.length; row++) {
        copy[row] = Objects.requireNonNull(
                source[row], "matrix row"
        ).clone();
    }
    return copy;
}
```

Đây là **đoạn minh họa cần đặt trong lớp có import `java.util.Objects`**, không phải chương trình độc lập. Nếu quy tắc cho phép hàng `null`, cần xác định cách xử lý khác một cách tường minh.

Trong record nhận ma trận có thể gọi `matrix = copyMatrix(matrix);` trong compact canonical constructor và `return copyMatrix(matrix);` trong accessor. Để đồng thời có ngữ nghĩa theo nội dung, triển khai `equals` bằng `Arrays.deepEquals(matrix, other.matrix)` và `hashCode` bằng `Arrays.deepHashCode(matrix)`.

Lưu ý `deepEquals`/`deepHashCode` phù hợp với cấu trúc mảng lồng không có chu trình; chúng không phải thuật toán tổng quát để so sánh đồ thị có vòng tham chiếu. Trong những mô hình đó cần quy tắc riêng.

### 8.2. List chứa phần tử thay đổi được

`List.copyOf` giữ cùng tham chiếu tới từng phần tử. Nếu một record chứa `List<MutableAddress>` và code khác còn tham chiếu tới các đối tượng địa chỉ, sửa địa chỉ vẫn làm thay đổi giá trị quan sát từ record.

Một cách tiếp cận rõ ràng là **chuyển về value object immutable** ngay lúc nhận:

```java
record AddressSnapshot(String city, String street) {}

record ShippingAddresses(List<AddressSnapshot> entries) {
    public ShippingAddresses {
        entries = List.copyOf(entries);
    }
}
```

Ví dụ này an toàn theo hướng bất biến nếu `AddressSnapshot` chỉ chứa `String` bất biến như hai component trên, không có đường ghi đè accessor trả mutable content. Nếu dữ liệu nhập ban đầu là `MutableAddress`, cần ánh xạ từng item vào `new AddressSnapshot(...)` trước khi tạo record hoặc trong constructor/chức năng factory phù hợp. Chỉ thay khai báo generic từ `MutableAddress` sang kiểu khác mà không thực hiện conversion không tự giải quyết được vấn đề.

### 8.3. Giới hạn của “bất biến sâu”

Tính bất biến cần đánh giá theo **toàn bộ đồ thị đối tượng mà record bộc lộ**:

- Nếu record chứa `List<List<String>>`, phải bảo đảm từng list con cũng không thể bị sửa. `List.copyOf(outer)` chỉ bao ngoài.
- Nếu record chứa `Date`, `Calendar`, `StringBuilder`, `ByteBuffer` hoặc object mutable, cần sao chép/chuyển đổi theo API và semantics tương ứng.
- Sao chép dữ liệu lớn mỗi lần gọi accessor có chi phí CPU/bộ nhớ; đôi khi phù hợp hơn là lưu một cấu trúc bất biến chuyên dụng hoặc cung cấp API đọc không lộ dữ liệu mutable.
- Nếu một component là đối tượng không thể sao chép an toàn hoặc ràng buộc tài nguyên, record có thể chưa phải biểu diễn phù hợp cho giá trị bất biến.

Không có quy tắc “mọi record đều tự động deep immutable”. Record hỗ trợ mô hình dữ liệu cô đọng; thiết kế bất biến thực sự vẫn là trách nhiệm của lập trình viên.

## 9. Kiểm tra tính hợp lệ và chuẩn hóa trong compact canonical constructor

Ngoài sao chép, compact constructor phù hợp để kiểm tra invariant và chuẩn hóa thành phần. Ví dụ:

```java
import java.util.List;
import java.util.Objects;

record Job(String name, List<String> labels) {
    public Job {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(labels, "labels");

        name = name.strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("Blank job name");
        }
        labels = List.copyOf(labels);
    }
}
```

Khi kết thúc phần thân compact constructor, Java mới gán những tham số đã xử lý vào trường `final`. Do đó `name` lưu dạng đã `strip()` và `labels` lưu snapshot bất biến. Nếu validation thất bại, constructor ném ngoại lệ và không tạo thành công record không hợp lệ.

Một số nguyên tắc:

1. **Không gọi phương thức accessor của `this` để đọc component chưa được gán** trong quá trình compact constructor. Khi đang thực hiện phần thân, các trường component chưa được khởi tạo bởi phép gán ngầm cuối constructor. Hãy dùng **tham số constructor** cho validation và normalization.
2. **Không gán trực tiếp `this.component` trong compact constructor.** Dùng phép gán lại tham số như `labels = List.copyOf(labels)`.
3. **Không để `this` thoát khỏi constructor** trước khi record được khởi tạo đầy đủ (ví dụ đăng ký listener hoặc lưu vào nơi dùng chung).
4. **Không trả một tham chiếu mutable từ accessor tự viết** nếu constructor đã bảo vệ dữ liệu đầu vào; làm vậy triệt tiêu hiệu lực của defensive copy.
5. **Không thay đổi giả tạo nội dung trả về bởi accessor** theo cách phá tính nhất quán của record hoặc vi phạm ý nghĩa `equals`.

Trình tự quan trọng: với compact canonical constructor, *validate/normalize/copy trên tham số* → *gán ngầm vào trường component* → *record hình thành với giá trị đã chuẩn hóa*.

## 10. Bất biến bản sao và hợp đồng value object của record

Một thuộc tính của record là các component mô tả **toàn bộ trạng thái lưu trữ** liên quan đến giá trị. Vì vậy thường mong đợi phép “sao chép bằng accessor” giữ nguyên quan hệ bằng nhau:

```java
// Minh họa với record R có các component c1(), c2().
// R copied = new R(original.c1(), original.c2());
// original.equals(copied) nên đúng theo thiết kế giá trị.
```

Với component thật sự bất biến và `equals` theo giá trị, thuộc tính đó tự nhiên được duy trì. Với component mutable, defensive copy có thể sinh tham chiếu mới; nếu `equals` mặc định dùng danh tính phần tử (như mảng), bản sao record có thể không bằng bản gốc. Vì thế phải chọn một trong các cách:

- Thiết kế component theo **giá trị bất biến**, chẳng hạn list bất biến của các value object bất biến, để `equals` sinh tự động phù hợp.
- Tự định nghĩa **`equals` và `hashCode` theo nội dung** với component là mảng đã bảo vệ bằng defensive copy, để bản sao qua accessor vẫn tương đương.
- Không dùng record như một value object nếu yêu cầu thực sự dựa vào danh tính tài nguyên, đối tượng có vòng đời riêng hay cấu trúc mutable không thích hợp.

Với mọi triển khai `equals` theo nội dung, hash phải dựa **đúng những trường đã dùng trong `equals`**. Cấu trúc `HashSet`/`HashMap` đòi hỏi cặp này ổn định khi đối tượng làm khóa: nếu hàm hash dựa trên dữ liệu nội bộ còn thay đổi sau khi thêm vào collection, thao tác tìm có thể không tìm lại phần tử.

## 11. Chi phí, tương thích API và quyết định thiết kế

Defensive copy tăng độ an toàn nhưng không miễn phí. Với mảng dài `n`, `clone()` thường phải cấp phát mảng mới và sao chép `n` phần tử, tức chi phí tỷ lệ với kích thước mảng. Nếu mỗi lần accessor đều gọi `clone()`, đọc nhiều lần có thể tạo nhiều mảng. Tuy vậy việc trả mảng mutable trực tiếp có thể mở đường sửa trái phép trạng thái, rất khó gỡ lỗi về sau.

Những lựa chọn thực tế:

- **Nhỏ và đơn giản:** record chứa mảng một chiều nguyên thủy, clone khi nhập/xuất và dùng `Arrays.equals`/`hashCode` nếu giá trị được xác định bằng nội dung.
- **Collection của phần tử bất biến:** record dùng `List.copyOf` một lần trong constructor; accessor mặc định trả list bất biến, tránh cấp phát bản sao trên mỗi lần truy cập.
- **Dữ liệu lớn hoặc cần cập nhật thường xuyên:** cân nhắc class có API kiểm soát đọc/ghi, persistent collection, immutable snapshot theo phiên bản hoặc tách riêng mô hình mutable và snapshot. Record chưa chắc là mô hình tốt cho đối tượng cần thay đổi liên tục.
- **Yêu cầu serialization hoặc giao tiếp API:** không nên giả định một thư viện serialization sẽ tạo/đọc record bằng cùng đường constructor trong mọi cấu hình. Cần kiểm thử đường giải mã của thư viện đang dùng để bảo đảm validation và defensive copy được thực thi.

Trong Java object serialization chuẩn dành cho record, canonical constructor tham gia quá trình dựng record khi giải mã; tuy nhiên hệ thống có thể dùng nhiều framework với cơ chế riêng. Đừng để validation/copy chỉ tồn tại ở một factory không được các đường dựng đối tượng khác gọi tới.

## 12. Các lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ rằng `record` hoặc `final` làm mảng tự bất biến | `final` cố định tham chiếu, phần tử vẫn thay đổi được. | Sao chép mutable component theo đường vào và đường ra. |
| Chỉ clone trong constructor | Accessor mặc định vẫn lộ mảng nội bộ. | Khai báo accessor trả `clone()` hoặc bản sao phù hợp. |
| Chỉ clone trong accessor | Caller vẫn giữ tham chiếu đầu vào, có thể sửa record từ ngoài. | Sao chép trong canonical constructor trước khi lưu. |
| Trong compact constructor viết `this.values = values.clone()` | Không phù hợp quy tắc gán trường component của compact constructor. | Viết `values = values.clone()`; Java gán ngầm sau phần thân. |
| Dùng `List.copyOf` cho `List<MutableItem>` rồi gọi là bất biến sâu | List không cho đổi cấu trúc nhưng item vẫn bị sửa được. | Sao chép/chuyển item thành value object bất biến trước. |
| Dùng `Collections.unmodifiableList(source)` như snapshot | View có thể phản ánh sửa đổi qua nguồn `source`. | Dùng `List.copyOf` hoặc tự tạo bản sao theo policy. |
| Dùng `array.clone()` cho mảng lồng và nghĩ đã deep copy | Các mảng con vẫn được chia sẻ. | Sao chép từng mảng con hoặc đệ quy theo cấu trúc. |
| Clone mảng trong constructor và accessor nhưng giữ `equals` tự sinh | Hai record có nội dung mảng giống nhau vẫn có thể không bằng nhau vì danh tính mảng. | Dùng giá trị bất biến có `equals` theo nội dung hoặc ghi đè cặp `equals`/`hashCode`. |
| Chỉ ghi đè `equals` theo `Arrays.equals` | `hashCode` sinh sẵn có thể dùng cách tính khác, phá hợp đồng hash. | Luôn ghi đè `hashCode` tương ứng bằng `Arrays.hashCode` (hoặc cặp deep). |
| Trả bản sao mutable nhưng giả định các lớp client sẽ sửa vào record | Thao tác trên bản sao không làm thay đổi record. | Cung cấp phương thức tạo snapshot mới, ví dụ `withValues` trả record mới, nếu cần cập nhật giá trị. |
| Quên xác định chính sách `null` | `clone()` trên `null` ném NPE; `List.copyOf` từ chối phần tử `null`. | Kiểm tra `Objects.requireNonNull` hoặc thiết kế giá trị mặc định/tùy chọn rõ ràng. |

## 13. Checklist kiểm thử record bất biến

Tạo một record chứa mutable component và kiểm thử cả hai hướng:

1. **Input aliasing:** truyền mảng/list vào record, sửa dữ liệu nguồn sau khi tạo, xác nhận accessor vẫn cho snapshot ban đầu.
2. **Output aliasing:** nhận mảng từ accessor, sửa bản sao, gọi accessor lần nữa, xác nhận record không đổi.
3. **Collection snapshot:** thêm/xóa trong list nguồn sau khi tạo, kiểm tra record không đổi; thử sửa list trả về phải bị chặn khi policy yêu cầu unmodifiable.
4. **Mutable elements:** nếu list chứa object mutable, thử sửa chính object đó; nếu giá trị record đáng ra bất biến mà kết quả thay đổi, chính sách copy còn thiếu.
5. **Nested arrays:** sửa hàng `int[]` của ma trận nguồn và của kết quả accessor; không được ảnh hưởng ma trận bên trong record snapshot.
6. **Value equality:** tạo hai record độc lập có dữ liệu tương đương; kiểm tra `equals` trả kết quả đúng theo chính sách nội dung.
7. **Hash agreement:** mọi cặp record bằng nhau phải có `hashCode` bằng nhau; sau mọi nỗ lực sửa nguồn/đầu ra, hash của record bất biến vẫn không thay đổi.
8. **Copy invariant:** tạo record mới từ chính các accessor của record gốc; kết quả phải tương đương theo `equals` nếu record được thiết kế là value object.
9. **Validation:** đưa dữ liệu `null`, thiếu hoặc sai định dạng; xác nhận constructor từ chối hay chuẩn hóa đúng chính sách, không tạo trạng thái không hợp lệ.
10. **Collection behavior:** dùng record làm phần tử `HashSet` hoặc khóa `HashMap`, rồi thử sửa mọi dữ liệu nguồn hoặc bản sao xuất ra. Tra cứu bằng một record tương đương vẫn phải thành công.

Đây là các kiểm tra hành vi bên ngoài của đối tượng. Chúng tìm thấy hai nhóm lỗi lớn: record chưa thật sự bất biến và record bất biến nhưng `equals`/`hashCode` không phản ánh nội dung cần so sánh.

## 14. Ghi nhớ

**Record không tự bảo đảm bất biến sâu.** Với component mutable, cần chặn aliasing từ **canonical constructor** (sao chép khi nhận) và từ **accessor** (sao chép khi trả hoặc xuất biểu diễn immutable an toàn). Compact canonical constructor cho phép gán lại tham số, rồi Java tự gán chúng vào trường component khi constructor kết thúc. `List.copyOf` hữu ích với collection của phần tử bất biến, còn mảng và đối tượng lồng phải xem xét cả các thành phần bên trong. Với mảng làm component, việc defensive copy còn phải đi kèm ngữ nghĩa `equals`/`hashCode` thích hợp; nếu muốn so nội dung, không dựa vào cơ chế mặc định theo danh tính của mảng. Chọn quy tắc sao chép và bằng nhau cùng lúc sẽ giúp record giữ được giá trị ổn định, an toàn khi truyền qua API và tin cậy khi dùng làm khóa băm.