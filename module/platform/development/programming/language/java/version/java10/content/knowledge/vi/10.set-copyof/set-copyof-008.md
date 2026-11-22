# Rủi ro khi phần tử thay đổi dữ liệu tham gia `equals`, `hashCode` trong `Set.copyOf`

*Chủ đề cha: `Set.copyOf` (Java 10+). Bài này giải thích vì sao một tập hợp không cho sửa vẫn có thể gặp lỗi ngữ nghĩa khi các đối tượng phần tử thay đổi những trường được dùng để xác định bằng nhau hoặc tính mã băm. Các quy tắc và ví dụ áp dụng cho Java hiện đại; chương trình hoàn chỉnh chạy với JDK 17 trở lên.*

## 1. Điều cần hiểu trước tiên

**`Set.copyOf(collection)` trả một `Set` không hỗ trợ thêm, xóa hay thay phần tử thông qua API của tập hợp, nhưng không tự biến mọi đối tượng bên trong thành bất biến.** Nó sao chép *tham chiếu phần tử* theo ý nghĩa bản sao nông (shallow copy), không phải deep copy từng đối tượng.

Nếu phần tử có trạng thái mutable được dùng trong `equals(Object)` hoặc `hashCode()`, rồi trạng thái ấy đổi trong khi phần tử vẫn thuộc tập, các thao tác như `contains`, so sánh tập hoặc cơ chế đảm bảo không trùng có thể cho kết quả khó hiểu. **Hợp đồng của `Set` không xác định hành vi khi trạng thái một phần tử bị thay đổi theo cách ảnh hưởng phép so sánh `equals` trong lúc phần tử nằm trong tập.** Các cấu trúc dựa trên mã băm còn phụ thuộc `hashCode` ổn định để tìm đúng phần tử.

Ví dụ ý tưởng:

```java
var key = new MutableKey("A");
var keys = java.util.Set.copyOf(java.util.List.of(key));

// Không thể keys.add(...) hoặc keys.remove(...).
// Nhưng nếu một chỗ khác còn giữ key:
key.rename("B"); // Có thể làm kết quả tìm kiếm/tính duy nhất không đáng tin.
```

`MutableKey` ở đây là lớp minh họa có trường `code` mutable được dùng trong `equals` và `hashCode`; chương trình đầy đủ xuất hiện ở mục 5. Việc không thể sửa `keys` **không chặn** lời gọi `key.rename(...)` trên tham chiếu đã giữ từ trước.

Sau bài học, bạn sẽ biết:

1. Phân biệt tính **unmodifiable của Set** với tính **immutable của đối tượng phần tử**.
2. Hiểu mối liên hệ giữa `equals`, `hashCode` và tính duy nhất của Set.
3. Nhận ra lỗi khi một khóa thay đổi sau khi được thêm/sao chép vào Set.
4. Thiết kế khóa dựa trên trường ổn định, hoặc tạo immutable snapshot trước khi đưa vào Set.
5. Xử lý trường hợp record chứa collection mutable, duplicate theo `equals`, nguồn mutable và truy cập đồng thời.
6. Kiểm thử hành vi mà không phụ thuộc thứ tự duyệt hay chi tiết triển khai nội bộ của một JDK.

## 2. `Set.copyOf` cam kết điều gì?

Chữ ký generic của API:

```java
public static <E> Set<E> copyOf(Collection<? extends E> coll)
```

Đây là chữ ký để đọc, không phải chương trình Java độc lập. `E` là kiểu phần tử của kết quả; `Collection<? extends E>` cho phép nguồn cung cấp phần tử kiểu `E` hoặc kiểu con. Phương thức xuất hiện từ **Java 10** và vẫn được dùng trong Java hiện đại.

Những bảo đảm quan trọng:

- Kết quả là **Set không cho sửa**. Các thao tác thay đổi như `add`, `remove`, `clear` sẽ ném `UnsupportedOperationException`.
- Kết quả **không chứa `null`**. Truyền nguồn `null` hoặc collection có phần tử `null` dẫn tới `NullPointerException`.
- Nếu nguồn `Collection` có phần tử trùng theo `equals` ở thời điểm sao chép, Set kết quả chỉ giữ một phần tử trong mỗi nhóm trùng; **không bảo đảm đại diện cụ thể nào** được giữ.
- **Không có thứ tự lặp xác định theo hợp đồng `Set.copyOf`.** Ngay cả khi nguồn có thứ tự, không được dựa vào một thứ tự cố định của Set kết quả.
- Các tham chiếu đối tượng phần tử vẫn có thể được chia sẻ. API không hứa tự clone từng `E`.
- Nếu đầu vào đã là một Set không cho sửa phù hợp, implementation có thể tái sử dụng đối tượng; không dựa vào `==` hoặc identity của kết quả.

**`Unmodifiable Set` không đồng nghĩa `Set<ImmutableElement>`.** API cấm thao tác lên cấu trúc tập, nhưng không thể ngăn caller sửa một đối tượng mutable mà caller còn tham chiếu.

### 2.1. Bảng các kiểu thay đổi

| Thao tác | `Set.copyOf` ngăn được? | Giải thích |
| --- | --- | --- |
| `result.add(x)` | Có | Ném `UnsupportedOperationException` |
| `result.remove(x)` | Có | Ném `UnsupportedOperationException` |
| `result.clear()` | Có | Ném `UnsupportedOperationException` |
| Thêm/xóa phần tử ở collection nguồn sau khi sao chép | Kết quả không tự cập nhật | Có snapshot của các tham chiếu phần tử lúc tạo |
| `existingElement.setCode("B")` qua tham chiếu từ bên ngoài | Không | Cùng đối tượng phần tử có thể đã nằm trong Set |
| `existingElement.mutableChild.add(x)` | Không | Nội dung sâu của phần tử không được đóng băng |
| Thay nội dung một trường **không** ảnh hưởng `equals`/`hashCode` | Không | Có thể chấp nhận về ngữ nghĩa thành viên, nhưng giá trị quan sát được đổi |
| Thay trường **có** ảnh hưởng `equals`/`hashCode` | Không, và có rủi ro nghiêm trọng | Vi phạm giả định ổn định của Set khi phần tử đã thuộc tập |

Bảng không có nghĩa mọi cách hiện thực `Set.copyOf` đều sử dụng cùng một cấu trúc mã băm. Hợp đồng API chỉ nói về hành vi quan sát được khi sử dụng đúng; **chi tiết bucket, table hay thuật toán tìm kiếm không phải bảo đảm của Java**.

## 3. `equals`, `hashCode` và ý nghĩa “hai phần tử trùng”

### 3.1. `equals` định nghĩa bằng nhau theo giá trị hoặc định danh nghiệp vụ

Các implementation của `Set` thường hiểu phần tử trùng dựa trên quan hệ `equals`. Nếu hai đối tượng `a` và `b` bằng nhau, Set không được chứa cả hai như hai phần tử phân biệt theo hợp đồng Set khi trạng thái phần tử ổn định.

```java
record TagKey(String code) {}

var a = new TagKey("A");
var b = new TagKey("A");

System.out.println(a.equals(b)); // true
```

`record` trong ví dụ có thành phần `String` bất biến, nên định nghĩa `equals`/`hashCode` sinh tự động của record ổn định miễn đối tượng giữ nguyên cấu trúc như thiết kế. Khai báo record trên là đoạn minh họa có thể đặt ở cấp lớp; để chạy riêng cần đặt vào một lớp/tệp thích hợp.

Khi lớp tự định nghĩa `equals`, hãy bảo đảm quan hệ bằng nhau hợp lý: phản xạ, đối xứng, bắc cầu, nhất quán khi những thông tin tham gia so sánh chưa đổi và `x.equals(null)` luôn `false`.

### 3.2. `hashCode` phải nhất quán với `equals`

Quy tắc cơ bản:

- Nếu `a.equals(b)` là `true`, phải có `a.hashCode() == b.hashCode()`.
- Nếu hash code bằng nhau, **không** có nghĩa hai đối tượng buộc phải `equals` nhau: va chạm mã băm là hợp lệ.
- Với các cấu trúc tra cứu dựa trên mã băm, mã băm và quan hệ bằng nhau của phần tử cần ổn định **trong suốt thời gian phần tử là thành viên**.

Ví dụ:

```java
@Override
public boolean equals(Object other) {
    return other instanceof MutableKey key
            && java.util.Objects.equals(code, key.code);
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(code);
}
```

Nếu `code` đổi từ `"A"` sang `"B"`, `hashCode()` cũng đổi; đối tượng có thể trở nên bằng một phần tử khác vốn đã có trong Set. Dù chính phương thức `rename` hợp lệ theo quy tắc của class, việc dùng đối tượng này làm **phần tử của Set đang hoạt động** có thể làm hỏng các giả định ngữ nghĩa.

### 3.3. Không phải mọi trường mutable đều nguy hiểm như nhau

Một đối tượng có thể chứa:

- `id` cố định, dùng trong `equals`/`hashCode`.
- `displayLabel` có thể đổi, **không** tham gia `equals`/`hashCode`.

Trong trường hợp đó, thay `displayLabel` không làm đối tượng trở nên bằng một đối tượng khác hoặc đổi mã băm. Đây thường là thiết kế chấp nhận được cho nhu cầu tập hợp theo **định danh ổn định**. Nhưng Set vẫn không deep-immutable: người dùng khác có thể quan sát tên hiển thị mới qua đối tượng phần tử.

**Tránh lỗi thiết kế:** dùng `equals` chỉ theo `id` nhưng tính `hashCode` theo cả `id` và `displayLabel` sẽ vi phạm hợp đồng nếu hai đối tượng có cùng `id` và nhãn khác nhau: bằng nhau nhưng có thể khác hash. Các trường mà `hashCode` sử dụng phải phù hợp với logic bằng nhau.

## 4. Điều gì xảy ra khi một khóa thay đổi trong Set?

Giả sử tại thời điểm tạo tập có ba phần tử:

```text
A    B    C
(3 khóa phân biệt theo equals và hashCode)
```

Sau đó một nơi khác sửa đối tượng `A` thành mã `B`:

```text
B    B    C
(3 tham chiếu vẫn tồn tại, nhưng nay có hai phần tử bằng nhau)
```

Tập không tự nhận biết và chạy lại quá trình khử trùng. Vì vậy:

- `size()` có thể vẫn báo số phần tử theo cấu trúc cũ, dù các giá trị hiện tại nay trùng theo `equals`.
- Tìm kiếm bằng `contains` với một đối tượng mới bằng phần tử đã sửa có thể có kết quả bất ngờ; không được viết code phụ thuộc nó.
- Nếu một implementation dựa vào vị trí/bảng băm tính lúc tạo tập, mã băm mới có thể không phù hợp vị trí cũ, dẫn tới không tìm được phần tử dù iterator vẫn thấy nó.
- Phép so sánh hai Set hoặc những xử lý giả định các khóa phân biệt có thể trở nên không đáng tin.
- `Set.copyOf` cấm sửa tập qua `remove`/`add`; không thể “chữa trực tiếp” bằng việc xóa rồi thêm trên chính kết quả.

Quan trọng: **không khẳng định cụ thể `contains` chắc chắn trả `false` hay `true` ở mọi JDK sau mutation**. Khi trạng thái bằng nhau của phần tử đổi trong Set, hợp đồng Set không xác định hành vi. Mục đích bài học là **tránh tình trạng đó**, không học thuộc một kết quả phụ thuộc cấu trúc nội bộ.

## 5. Chương trình Java 17+: một Set không cho sửa vẫn có thể chứa hai khóa bằng nhau sau mutation

Tạo file **`MutableEqualityDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class MutableEqualityDemo {
    static final class MutableKey {
        private String code;

        MutableKey(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }

        void rename(String next) {
            code = next;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && Objects.equals(code, key.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    public static void main(String[] args) {
        var first = new MutableKey("A");
        var second = new MutableKey("B");
        var third = new MutableKey("C");

        var frozenSet = Set.copyOf(List.of(first, second, third));
        var originalHash = first.hashCode();

        System.out.println("before=" + frozenSet.stream()
                .map(MutableKey::code).sorted().toList());
        System.out.println("sizeBefore=" + frozenSet.size());

        first.rename("B");

        System.out.println("after=" + frozenSet.stream()
                .map(MutableKey::code).sorted().toList());
        System.out.println("sizeAfter=" + frozenSet.size());
        System.out.println("nowEqual=" + first.equals(second));
        System.out.println("hashChanged="
                + (first.hashCode() != originalHash));
        System.out.println("sameReference=" + frozenSet.stream()
                .anyMatch(item -> item == first));

        try {
            frozenSet.add(new MutableKey("D"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("addBlocked=true");
        }
    }
}
```

Chạy:

```bash
javac --release 17 MutableEqualityDemo.java
java MutableEqualityDemo
```

Stdout (cố ý `sorted()` để không phụ thuộc thứ tự lặp của Set):

```text
before=[A, B, C]
sizeBefore=3
after=[B, B, C]
sizeAfter=3
nowEqual=true
hashChanged=true
sameReference=true
addBlocked=true
```

Phân tích:

1. Trước khi đổi, `first`, `second`, `third` phân biệt theo `code`; `Set.copyOf` nhận ba phần tử.
2. `frozenSet` không cho phép thêm `D`, nhưng caller vẫn giữ tham chiếu `first`.
3. Gọi `first.rename("B")` đổi một trường được cả `equals` lẫn `hashCode` sử dụng.
4. `first.equals(second)` trở thành `true`. Iterator của Set vẫn đi qua ba tham chiếu đã chứa, nên bản liệt kê mã sau khi sắp xếp cho `[B, B, C]`.
5. `sizeAfter` không tự được cập nhật theo quan hệ bằng nhau mới; `addBlocked` xác nhận tập vẫn không cho sửa qua API.
6. `sameReference=true` cho thấy `Set.copyOf` không tạo clone của `first`.

Ví dụ **không gọi `contains` để khẳng định một giá trị đúng/sai cố định**, vì mục tiêu là minh họa rủi ro theo hợp đồng Java mà không dựa vào cách JDK triển khai bảng băm.

### 5.1. Đây là vấn đề của đối tượng phần tử, không phải do `var`

Bạn có thể khai báo:

```java
Set<MutableKey> frozenSet =
        Set.copyOf(List.of(first, second, third));
```

thay vì `var frozenSet = ...`. Rủi ro hoàn toàn không đổi: kiểu biên dịch vẫn là Set chứa các `MutableKey`, và trạng thái của đối tượng vẫn có thể đổi qua tham chiếu khác.

Tương tự, `final var frozenSet = ...` chỉ ngăn **gán lại biến** `frozenSet`. Nó không làm phần tử bên trong bất biến; `final` không phải cơ chế sao chép sâu.

## 6. Thiết kế tốt hơn: định danh ổn định tham gia `equals`/`hashCode`

Nếu đối tượng thực sự cần có thuộc tính mutable như nhãn hiển thị, hãy xác định **identity key ổn định** để so sánh. Ví dụ:

- `id` được gán một lần và không đổi.
- `displayLabel` được cập nhật nhưng không được đưa vào `equals`/`hashCode`.

Tạo **`StableIdentityDemo.java`**:

```java
import java.util.List;
import java.util.Set;

public class StableIdentityDemo {
    static final class Item {
        private final String id;
        private String note;

        Item(String id, String note) {
            this.id = id;
            this.note = note;
        }

        String note() {
            return note;
        }

        void updateNote(String next) {
            note = next;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item item
                    && id.equals(item.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        var item = new Item("K1", "draft");
        var items = Set.copyOf(List.of(item));
        var hashBefore = item.hashCode();

        item.updateNote("published");

        System.out.println("hashStable="
                + (item.hashCode() == hashBefore));
        System.out.println("lookupByStableId="
                + items.contains(new Item("K1", "another")));
        System.out.println("updatedNote="
                + items.iterator().next().note());
    }
}
```

Chạy:

```bash
javac --release 17 StableIdentityDemo.java
java StableIdentityDemo
```

Stdout:

```text
hashStable=true
lookupByStableId=true
updatedNote=published
```

Ý nghĩa:

- `id` là `final` và được dùng nhất quán ở `equals`/`hashCode`.
- Thay `note` không làm thay đổi identity của đối tượng.
- Set có thể tìm theo một đối tượng `Item` mới cùng `id` trong tình huống hợp lệ này.
- `updatedNote=published` cũng chứng minh **đối tượng phần tử vẫn mutable** và trạng thái hiển thị qua Set đã thay đổi.

Giải pháp có điều kiện: `id` phải thật sự **ổn định, không null theo hợp đồng và duy nhất trong phạm vi nghiệp vụ cần xét**. Trường `final String id` chỉ an toàn nếu code không để giá trị không hợp lệ lọt vào; với object tham chiếu mutable được đặt trong trường `final`, bản thân `final` không bảo vệ nội dung sâu.

Nếu nghiệp vụ quy định hai đối tượng bằng nhau dựa trên **toàn bộ trạng thái**, không thể tùy tiện bỏ trường mutable khỏi `equals` chỉ để Set hoạt động. Khi ấy cần chuyển sang immutable snapshot hoặc một cấu trúc quản lý vòng đời khác.

## 7. Record là bất biến nông, vẫn cần xét các component mutable

Java `record` tự cung cấp `equals`/`hashCode` dựa trên các component. Record không cho gán lại các trường component theo cách thông thường, nhưng **tham chiếu `final` đến một collection mutable không biến collection đó thành bất biến**.

Ví dụ sau tạo record chứa `List<String>`. `List.hashCode()` và `List.equals()` phụ thuộc phần tử trong danh sách; sửa list từ bên ngoài có thể làm mã băm của record thay đổi.

Tạo **`RecordMutationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class RecordMutationDemo {
    record Team(List<String> names) {}

    record SafeTeam(List<String> names) {
        public SafeTeam {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        var mutableNames = new ArrayList<>(List.of("An"));
        var team = new Team(mutableNames);
        var teams = Set.copyOf(List.of(team));
        var hashBefore = team.hashCode();

        mutableNames.add("Binh");

        System.out.println("recordHashChanged="
                + (hashBefore != team.hashCode()));
        System.out.println("recordNames="
                + teams.iterator().next().names());

        var external = new ArrayList<>(List.of("An"));
        var safeTeam = new SafeTeam(external);
        var safeTeams = Set.copyOf(List.of(safeTeam));
        var safeHashBefore = safeTeam.hashCode();

        external.add("Binh");

        System.out.println("safeHashStable="
                + (safeHashBefore == safeTeam.hashCode()));
        System.out.println("safeNames="
                + safeTeams.iterator().next().names());
    }
}
```

Chạy:

```bash
javac --release 17 RecordMutationDemo.java
java RecordMutationDemo
```

Stdout:

```text
recordHashChanged=true
recordNames=[An, Binh]
safeHashStable=true
safeNames=[An]
```

Phân tích:

- `Team` giữ nguyên tham chiếu `mutableNames`. `List` thay đổi làm `hashCode` của record thay đổi theo.
- `Set.copyOf(List.of(team))` **không** sao chép sâu record hay list nằm trong record.
- Trong `SafeTeam`, compact constructor thay danh sách đầu vào bằng `List.copyOf(names)`, ngăn code bên ngoài thêm/xóa phần tử qua tham chiếu `external` làm thay đổi component của record.
- Kết quả an toàn trong ví dụ vì các phần tử của list là `String`, vốn bất biến. Nếu component là `List<MutableUser>` mà `MutableUser.equals/hashCode` phụ thuộc thuộc tính mutable, `List.copyOf` vẫn **chưa** giải quyết tính bất biến sâu.

**Đừng hiểu “record” là mặc định deep immutable.** Điều cần giữ ổn định là toàn bộ dữ liệu mà phép bằng nhau và mã băm sử dụng, kể cả các đối tượng/collection lồng nhau.

## 8. Cách thiết kế tốt: lưu giá trị khóa bất biến vào Set

Khi chỉ cần truy vấn tập hợp mã, trạng thái hoặc khóa, có thể chuyển dữ liệu đầu vào mutable thành một **giá trị khóa bất biến** trước khi gọi `Set.copyOf`:

```java
// Đoạn minh họa bên trong một lớp/phương thức phù hợp.
record UserKey(String id) {}

var sourceUserIds = java.util.List.of("U1", "U2");
var keys = java.util.Set.copyOf(
        sourceUserIds.stream()
                .map(UserKey::new)
                .toList()
);
```

Đoạn này dùng `UserKey` chứa `String` bất biến; nếu business ID được giữ ổn định, giá trị Set không phụ thuộc một đối tượng User mutable ngoài tập. `Set.copyOf` nhận `List<UserKey>`, còn `Set<UserKey>` là kết quả. Thứ tự Set không được bảo đảm; nếu cần xuất danh sách có thứ tự, hãy sắp xếp khi trình bày.

Với đối tượng có nhiều trường quyết định `equals`, có thể xây một immutable **snapshot/key object** chỉ chứa các dữ liệu đó theo hợp đồng nghiệp vụ. Tránh đưa trực tiếp các bean mutable phức tạp vào Set khi không kiểm soát được nơi nào có thể đổi khóa.

### 8.1. Validate trước khi đóng băng

Một khóa đáng tin còn cần dữ liệu đầu vào hợp lệ:

```java
record UserKey(String id) {
    public UserKey {
        java.util.Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
    }
}
```

Đây là **định nghĩa thay thế** của `UserKey` cho tình huống cần validate, không được ghép cùng tên với record ở đoạn trước trong cùng scope. Nó bảo đảm ID không `null` và không trắng; các quy tắc định danh khác tùy nhu cầu thực tế. `Set.copyOf` từ chối phần tử `null`, nhưng không tự xác thực nội dung trường `id` bên trong từng object.

### 8.2. Nếu đối tượng cần sửa, hãy quản lý vòng đời có chủ đích

Có hai hướng thường gặp:

1. **Thay đổi object ngoài Set:** tạo khóa immutable hoặc snapshot, rồi xây Set từ snapshot. Thay trạng thái của object gốc không thay giá trị khóa đã lưu.
2. **Thay đổi tập thành viên sau mỗi cập nhật:** tạo một Set **mới** từ những giá trị đã chuẩn hóa/snapshot, thay tham chiếu Set của phía quản lý. Không cố `add`/`remove` trên Set do `Set.copyOf` trả về.

Nếu đang dùng một `HashSet` mutable, một quy trình có thể là **xóa phần tử theo khóa cũ trước khi đổi thông tin dùng để hash**, rồi thêm lại theo khóa mới. Nhưng đây là cách vận hành collection mutable có kỷ luật, **không áp dụng trực tiếp** cho `Set.copyOf` vì nó không cho sửa. Cũng đừng chờ đến sau mutation mới gọi `remove` rồi giả định sẽ tìm thấy phần tử cũ: bảng băm có thể đã không còn tìm đúng vị trí.

## 9. Phần tử trùng khi sao chép và khi thay đổi sau sao chép

### 9.1. Trùng ngay từ nguồn

Giả sử hai đối tượng khác nhau nhưng `equals` coi chúng bằng nhau:

```java
// Giả sử MutableKey.equals/hashCode chỉ dựa vào code:
var a = new MutableKey("K");
var b = new MutableKey("K");
var copied = java.util.Set.copyOf(java.util.List.of(a, b));

System.out.println(copied.size()); // 1
```

`Set.copyOf` giữ một đại diện từ nhóm trùng, **không hứa là `a` hay `b`**. Nếu chúng mang các thuộc tính khác không tham gia `equals` (như nhãn, thời gian tạo), đừng chọn `Set.copyOf` làm cơ chế quyết định “giữ bản ghi nào”.

Nếu nghiệp vụ cần ưu tiên bản ghi mới nhất hoặc bản ghi chất lượng cao hơn, hãy **quy định rõ logic khử trùng trước** (ví dụ Map theo ID với hàm giải quyết trùng có chủ đích), sau đó sao chép những giá trị mong muốn.

### 9.2. Trùng sau khi đã tạo Set

Đây là tình huống khác với `Set.copyOf` nhận nguồn chứa duplicate. `Set.copyOf` đảm bảo xử lý trùng ở **thời điểm nó quan sát các phần tử nguồn**. Nó không theo dõi và tự chạy lại việc loại trùng khi object bên trong bị sửa sau đó.

Như chương trình ở mục 5, hai phần tử ban đầu có mã `A`, `B` rồi cùng mang mã `B`; tập có thể vẫn báo ba vị trí và không còn đáp ứng kỳ vọng “đang chứa các giá trị phân biệt”. Không được suy diễn rằng vì tập không cho sửa nên phép bằng nhau giữa các phần tử cũng bị đóng băng.

### 9.3. Tránh dựa vào thứ tự và identity

`Set.copyOf` không bảo đảm thứ tự duyệt. Do đó, trong các ví dụ cần kiểm chứng danh sách mã, hãy dùng:

```java
var sortedCodes = copied.stream()
        .map(MutableKey::code)
        .sorted()
        .toList();
```

Đó là cách tạo output có thứ tự dựa trên dữ liệu tại thời điểm duyệt, không phải bằng chứng rằng Set bản thân có thứ tự. Khi những object mutable thay đổi giữa lúc duyệt hoặc sắp xếp ở nhiều thread, vẫn cần đồng bộ.

Đừng dùng `==` để so các Set do `copyOf` trả về. Chỉ dùng `==` có chủ đích trong ví dụ để chứng minh **tham chiếu phần tử** là cùng đối tượng, không dùng nó làm định nghĩa bằng nhau theo nghiệp vụ.

## 10. `Set.copyOf`, `Collections.unmodifiableSet` và `HashSet` khác nhau ở đâu?

| API / cấu trúc | Cho sửa chính tập? | Phụ thuộc collection nguồn sau khi tạo? | Có đóng băng object phần tử? |
| --- | --- | --- | --- |
| `Set.copyOf(collection)` | Không | Không phản ánh trực tiếp thao tác thêm/xóa nguồn; có thể giữ cùng object phần tử | Không |
| `Collections.unmodifiableSet(set)` | Không qua view | Là **view**, thường phản ánh thay đổi của tập nền | Không |
| `new HashSet<>(collection)` | Có | Cấu trúc độc lập với nguồn sau sao chép | Không |
| `Set.of(elements...)` | Không | Nhận phần tử trực tiếp, không có Collection nguồn | Không |

Các lựa chọn đều không tự làm cho một phần tử mutable trở nên an toàn làm khóa nếu trạng thái tham gia `equals`/`hashCode` thay đổi.

`HashSet` cho phép sửa chính tập, nhưng nó cũng dựa trên `equals`/`hashCode`. Nếu người dùng thay đổi hash key của phần tử lúc nó vẫn nằm trong HashSet, việc gọi `contains`/`remove` có thể gặp lỗi tương tự. **Thay Set.copyOf bằng HashSet không chữa lỗi thiết kế key mutable.**

`Collections.unmodifiableSet(set)` cũng không phải cơ chế deep freeze. Nó chỉ chặn thao tác qua view; một tham chiếu khác vẫn có thể sửa tập nền hoặc các đối tượng phần tử.

Nếu mục tiêu là tập độc lập về cấu trúc với nguồn và không cho thêm/xóa, `Set.copyOf` thích hợp. Nếu mục tiêu là phần tử bất biến về mặt nghiệp vụ, cần giải quyết tại **kiểu phần tử và dữ liệu dùng để so sánh**.

## 11. Khi nghi ngờ lỗi, kiểm tra gì?

Dấu hiệu thường gặp:

- Có phần tử thấy được khi duyệt, nhưng kiểm tra `contains` sau cập nhật khóa cho kết quả bất ngờ.
- `size()` không khớp với số mã/giá trị phân biệt quan sát được sau khi dữ liệu thay đổi.
- Hai đối tượng cùng mã sau một thao tác cập nhật, dù lúc xây Set chúng khác nhau.
- Phép so sánh giữa hai Set thay đổi theo trạng thái của object bên trong.
- Code nghĩ `Set.copyOf` đã bảo vệ dữ liệu, nhưng trường hoặc collection con của phần tử tiếp tục bị sửa.

Quy trình gỡ lỗi:

1. Xác định **kiểu thực tế của phần tử** và cài đặt `equals`, `hashCode`; xem cả trường lồng nhau mà chúng gọi tới.
2. Xác định object có được sửa **sau khi đặt vào Set** không; đặc biệt qua alias từ collection nguồn, cache, một service khác hoặc một getter trả object mutable.
3. Ghi lại các trường tham gia so sánh và mã băm **trước/sau** thay đổi ở môi trường thử nghiệm phù hợp.
4. Đối chiếu `equals` giữa các phần tử và kiểm tra có hai phần tử mới trở nên bằng nhau không.
5. Duyệt Set để kiểm tra các tham chiếu hiện có; tránh khẳng định kết quả cụ thể của `contains` trong trạng thái đã vi phạm hợp đồng.
6. Xây ví dụ tối thiểu có thể chạy, ví dụ mã ở mục 5, với output được sắp xếp để loại ảnh hưởng thứ tự duyệt.
7. Thiết kế lại key/snapshot và chạy lại test với cấu trúc ổn định, thay vì dựa vào việc JVM nào “có vẻ vẫn chạy đúng”.

**Cẩn trọng về logging:** không cần xuất thông tin định danh nhạy cảm của khách hàng vào log thật chỉ để debug. Trong bài minh họa, giá trị giả `A`/`B`/`C` đủ chứng minh cơ chế.

### 11.1. Test đúng bất biến nghiệp vụ

Một số test hữu ích:

- Các object khác nhau nhưng cùng **ID ổn định** phải `equals` và có cùng `hashCode`.
- Thay một trường hiển thị **không thuộc identity** không được làm `equals`/`hashCode` thay đổi.
- Nếu thiết kế immutable snapshot, thay đổi collection/đối tượng nguồn sau khi tạo phải không làm các trường dùng cho identity của snapshot thay đổi.
- `Set.copyOf` từ chối `null` và không cho `add`/`remove`; đây là hợp đồng API riêng.
- Không viết test kỳ vọng thứ tự duyệt của `Set.copyOf`.
- Không viết test kỳ vọng `contains` luôn `false` sau khi mutation gây sai hợp đồng; điều cần kiểm thử là code **không cho phép mutation ấy xảy ra** đối với khóa đang được dùng.

## 12. Truy cập đồng thời càng làm rủi ro khó phát hiện

Nếu nhiều thread cùng đọc Set và thay đổi các object phần tử, người dùng có thể gặp các trạng thái khó tái hiện: một thread tính hash trong lúc thread khác đổi trường tham gia `equals`, hoặc việc duyệt thấy một thời điểm trong khi phép tìm kiếm quan sát trạng thái khác.

`Set.copyOf` không tự quản lý đồng bộ của object phần tử. Nó không làm:

- Trạng thái của phần tử immutable.
- Việc sửa thuộc tính của phần tử trở nên atomic.
- Các giá trị quan sát qua nhiều trường nhất quán.
- Mọi phép xử lý ở nhiều thread tự động thread-safe.

Với dữ liệu chia sẻ, ưu tiên **immutable key/value**, publication đúng cách và cơ chế đồng bộ thích hợp cho các phần còn mutable. Nếu xây snapshot từ collection nguồn đang bị sửa đồng thời, cần quản lý cách đọc nguồn để đảm bảo dữ liệu nhất quán theo yêu cầu ứng dụng. Chỉ gọi `Set.copyOf` không thay thế thiết kế concurrency.

## 13. Những ngộ nhận phổ biến

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “`Set.copyOf` immutable nên phần tử không thể đổi.” | Chỉ Set không cho sửa; phần tử có thể là cùng tham chiếu tới object mutable |
| “`final var result = Set.copyOf(...)` giải quyết được.” | `final` ngăn gán lại biến, không đóng băng object phần tử |
| “Sửa trường hash thì `contains` chắc chắn trả `false`.” | Hành vi không xác định theo hợp đồng; không dựa vào kết quả cố định |
| “Nếu `Set.copyOf` được tạo từ List, thứ tự luôn như List.” | Không có bảo đảm thứ tự lặp của Set kết quả |
| “Dù phần tử đổi, Set sẽ tự khử trùng lại.” | Không có cơ chế tự cập nhật quan hệ bằng nhau của object sau khi sao chép |
| “Record luôn deep immutable.” | Record có thể giữ collection hoặc object mutable ở component |
| “`List.copyOf` trong record xử lý mọi nested mutable object.” | Chỉ bảo vệ cấu trúc List; phần tử nested mutable vẫn có thể ảnh hưởng equals/hash |
| “`HashSet` mutable nên sửa hash của phần tử khi đang trong set là ổn.” | HashSet cũng cần key ổn định trong thời gian membership |
| “Chỉ cần sửa `hashCode`, không cần xem `equals`.” | Hai phương thức phải nhất quán; bằng nhau thì cùng mã băm |
| “Copy source sẽ tạo bản sao sâu của từng phần tử.” | `Set.copyOf` không clone object phần tử |
| “Nếu có duplicate, Set luôn giữ bản ghi đầu tiên.” | `Set.copyOf` chọn đại diện không xác định giữa phần tử trùng |
| “`Set.copyOf` là thread-safe cho mọi object phần tử.” | Không có bảo đảm đồng bộ cho trạng thái mutable bên trong |

## 14. Bài tập có đáp án

### Bài 1 — Xác định vấn đề

Một lớp `Product` dùng `sku` và `price` trong `equals`/`hashCode`. Tạo:

```java
var products = Set.copyOf(sourceProducts);
```

Sau đó một chỗ khác cập nhật `price` của một `Product` nằm trong tập. Điều gì nguy hiểm?

**Đáp án:** vì giá nằm trong định nghĩa bằng nhau và hash, cập nhật có thể làm hash và quan hệ bằng nhau thay đổi khi phần tử đang nằm trong Set. Hợp đồng Set không xác định hành vi khi equals thay đổi theo cách đó. Nếu identity sản phẩm là `sku` ổn định theo nghiệp vụ, cân nhắc chỉ dựa vào `sku`; nếu giá là một phần giá trị cần so sánh, dùng immutable snapshot mang giá đó.

### Bài 2 — Phân biệt unmodifiable và immutable

Cho:

```java
var builder = new StringBuilder("A");
var set = Set.copyOf(List.of(builder));
builder.append("B");
```

Tại sao `set.iterator().next().toString()` có thể cho `"AB"`?

**Đáp án:** Set giữ cùng `StringBuilder`, không clone đối tượng. `StringBuilder` dùng identity-based `Object.equals/hashCode` vì không ghi đè, nên thay nội dung builder không làm chính hai phương thức đó đổi theo nội dung; nhưng giá trị nhìn thấy qua Set vẫn đổi. Đây là minh họa tính *shallow*, khác trường hợp khóa dùng nội dung mutable trong `equals/hashCode`.

### Bài 3 — Vì sao `size` không phản ánh khóa mới?

Một Set được tạo từ các object có mã `A`, `B`, `C`. Sau đó mã của `A` bị đổi thành `B` và `equals` dựa trên mã. Vì sao kích thước không nhất thiết giảm còn 2?

**Đáp án:** Set không tự quét các phần tử để khử trùng sau mutation. Trạng thái mới vi phạm giả định ổn định của quan hệ bằng nhau. Kích thước cấu trúc có thể vẫn là 3, như chương trình ở mục 5.

### Bài 4 — Record có List mutable

```java
record Group(List<String> names) {}
var names = new ArrayList<>(List.of("An"));
var group = new Group(names);
var set = Set.copyOf(List.of(group));
names.add("Binh");
```

Nếu record dùng `equals/hashCode` tự sinh, rủi ro gì?

**Đáp án:** record so sánh component `names`; List có `equals/hashCode` phụ thuộc phần tử. Sau `names.add`, hash và quan hệ bằng nhau của `group` có thể đổi. Dùng defensive copy `names = List.copyOf(names)` trong constructor và phần tử bất biến để giữ giá trị ổn định.

### Bài 5 — Trường không dùng cho identity

Đối tượng `Item` có `final String id` và `String note` mutable; `equals/hashCode` chỉ phụ thuộc `id`. Sau khi cho vào Set, cập nhật `note` có làm hỏng quan hệ thành viên không?

**Đáp án:** nếu `id` ổn định và việc triển khai equals/hash chỉ dựa trên `id`, thay `note` không làm quan hệ bằng nhau hoặc hash thay đổi; thao tác tra cứu theo `id` vẫn hợp lệ. Tuy nhiên Set không phải deep immutable: người đọc có thể thấy `note` mới và cần đồng bộ nếu đọc/ghi từ nhiều thread.

### Bài 6 — Duplicate trong nguồn

Có hai object cùng `code = "X"`, `equals/hashCode` dựa vào code, nhưng mỗi object có nhãn khác nhau. Gọi `Set.copyOf(List.of(a,b))` sẽ giữ nhãn nào?

**Đáp án:** không có bảo đảm đại diện cụ thể. Không dựa vào thứ tự nguồn để chọn object được giữ. Muốn chọn theo tiêu chí nghiệp vụ, hãy giải quyết trùng trước khi gọi `Set.copyOf`.

### Bài 7 — Xử lý khi cần thay ID

Bạn muốn đổi ID của một object đang được dùng làm phần tử khóa của một `Set.copyOf`. Phương án hợp lệ?

**Đáp án:** giữ đối tượng khóa cũ bất biến, tạo giá trị khóa mới và **xây một Set kết quả mới** từ dữ liệu mới được chuẩn hóa. Không sửa trường ID trong object đã nằm trong Set và không cố `remove` trên kết quả `Set.copyOf`. Bên quản lý tập quyết định khi nào chuyển tham chiếu sang snapshot mới.

## 15. Checklist áp dụng

Trước khi đưa object vào `Set.copyOf`:

1. **`equals` dùng những trường nào?** Chúng có thể đổi sau khi object vào Set không?
2. **`hashCode` có nhất quán với `equals` không?** Các object bằng nhau phải có cùng hash.
3. **Đối tượng có tham chiếu đến collection/array/object mutable không?** Record và `final` chỉ bảo vệ tham chiếu, không mặc nhiên bảo vệ nội dung.
4. **Có alias nào ngoài Set vẫn giữ object để sửa không?** Collection nguồn, repository, cache hoặc caller có thể tiếp tục giữ tham chiếu.
5. **Có cần snapshot các giá trị tham gia identity không?** Nếu có, hãy tạo khóa bất biến, validate và sao chép dữ liệu lồng nhau thích hợp.
6. **Source có `null` hoặc duplicate không?** `Set.copyOf` từ chối null và giữ đại diện bất kỳ của nhóm trùng.
7. **Có phụ thuộc thứ tự lặp không?** Nếu có, chọn cấu trúc/mô hình khác hoặc sắp xếp lúc xuất.
8. **Có luồng nào cùng sửa phần tử hoặc source trong lúc sao chép không?** Thiết kế phối hợp truy cập rõ ràng.
9. **Có test khẳng định invariant trước/sau thao tác cập nhật hợp lệ không?** Tránh test phụ thuộc hành vi không xác định sau mutation.
10. **Có thực sự cần lưu toàn bộ object vào Set không?** Đôi khi lưu immutable ID/value object đơn giản hơn và an toàn hơn.

**Ghi nhớ:** `Set.copyOf` tạo một **Set không cho sửa** và bảo toàn các *tham chiếu phần tử*, không đóng băng nội dung của chúng. Nếu trạng thái tham gia `equals`/`hashCode` đổi khi phần tử đã nằm trong tập, các bảo đảm tra cứu/tính duy nhất không còn đáng tin theo hợp đồng Java. Cách thiết kế ổn định là sử dụng **khóa bất biến**, giữ trường identity cố định hoặc tạo defensive snapshot trước khi đưa vào Set; khi dữ liệu khóa cần thay đổi, hãy xây một Set mới từ các giá trị mới.