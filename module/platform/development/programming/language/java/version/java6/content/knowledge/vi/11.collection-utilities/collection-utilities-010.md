# Kiểm thử aliasing và các view dùng chung dữ liệu trong Java Collections

## Mục tiêu

Khi làm việc với Java Collections, hai biến có thể trỏ đến **cùng một đối tượng** (aliasing), hoặc hai đối tượng collection khác nhau có thể **cùng sử dụng dữ liệu nền** (backed view). Có những collection chỉ cho đọc nhưng vẫn thay đổi theo nguồn; cũng có collection được sao chép độc lập về mặt cấu trúc nhưng vẫn chia sẻ tham chiếu đến phần tử.

Bài này tập trung vào cách **kiểm thử những quan hệ đó bằng hành vi quan sát được**, để tránh lỗi dữ liệu thay đổi ngoài dự kiến, nhầm view với bản sao, hoặc viết test dựa vào ngoại lệ không được API cam kết. Các API minh họa vẫn được sử dụng trong Java hiện đại; chương trình chạy độc lập dùng Java 17 trở lên.

Sau bài học, bạn có thể:

- Phân biệt alias cùng tham chiếu, backed view, fixed-size view, unmodifiable view và bản sao nông (shallow copy).
- Kiểm tra dữ liệu thay đổi theo **hai chiều**: sửa qua view rồi quan sát nguồn; sửa nguồn rồi quan sát view, với thao tác được API cho phép.
- Kiểm tra các phép thêm, xóa, thay thế phần tử và ngoại lệ `UnsupportedOperationException` theo đúng hợp đồng từng API.
- Chọn defensive copy khi cần tách trạng thái và tránh test phụ thuộc vào hành vi không xác định.

## 1. Nắm đúng các loại quan hệ dữ liệu

**Aliasing** xảy ra khi hai biến giữ tham chiếu đến đúng cùng một đối tượng:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> alias = source; // alias == source
alias.set(0, "X");           // source cũng chứa "X"
```

**Backed view** là một đối tượng cung cấp cách nhìn hoặc thao tác trên dữ liệu của một collection/mảng nền. View thường không phải cùng đối tượng với nguồn; vì vậy **`assertSame(source, view)` không phải cách kiểm thử view**. Phải kiểm tra những thay đổi mà tài liệu API bảo đảm được phản ánh qua các phía.

| Cách tạo | Quan hệ với nguồn | Thao tác tiêu biểu và đặc điểm cần test |
| --- | --- | --- |
| `List<T> alias = source` | Cùng đối tượng, cùng tham chiếu | `alias == source`; mọi thay đổi trên một tên biến thấy ở tên kia. |
| `source.subList(from, to)` | View của một đoạn list | `set` qua view ảnh hưởng list gốc và ngược lại; `clear` qua view xóa đoạn tương ứng ở nguồn nếu nguồn hỗ trợ. |
| `Arrays.asList(array)` | List có kích thước cố định, được mảng chống lưng | `set` cập nhật mảng; ghi phần tử mảng phản ánh vào list; `add`/`remove` làm đổi kích thước bị từ chối. |
| `Collections.unmodifiableList(source)` | View chỉ đọc đối với thao tác qua wrapper | Gọi mutator qua wrapper ném `UnsupportedOperationException`, nhưng sửa `source` vẫn có thể thấy qua wrapper. |
| `map.keySet()`, `map.values()`, `map.entrySet()` | Các view được map chống lưng | `put`/`remove` trên map phản ánh vào view; xóa qua view có thể xóa mapping của map; không hỗ trợ `add`. |
| `new ArrayList<>(source)` | Container mới, copy nông | Thay đổi cấu trúc/ô phần tử trong một list không đổi cấu trúc list kia; đối tượng phần tử có thể vẫn được chia sẻ. |
| `List.copyOf(source)` (Java 10+) | Danh sách không sửa được, không thay đổi theo list nguồn có thể sửa | Với nguồn mutable, thay đổi cấu trúc nguồn không làm đổi kết quả đã copy. Copy vẫn là nông và không chấp nhận phần tử `null`. |

`List.of(...)` (Java 9+) cũng tạo danh sách không sửa được. Nó không phải một backed view của một `ArrayList` mutable có sẵn. Không đồng nhất **không sửa được** với **bất biến sâu**: nếu phần tử là đối tượng mutable, trạng thái phần tử vẫn có thể đổi từ bên ngoài.

## 2. Thiết kế kiểm thử theo hợp đồng, không theo tên lớp triển khai

Với mỗi API được khảo sát, tạo một nguồn nhỏ, tạo alias/view/copy, rồi kiểm tra độc lập các nhóm sau:

1. **Cùng identity hay không?** Chỉ dùng `==` hoặc `assertSame` khi thực sự muốn chứng minh hai tham chiếu là một đối tượng. Hai list `equals` nhau chỉ chứng minh nội dung bằng nhau tại thời điểm kiểm tra.
2. **View → nguồn:** Thực hiện thao tác được hỗ trợ qua view, sau đó kiểm tra nội dung nguồn. Ví dụ `subList.set`, `subList.clear`, `keySet.remove`, `Map.Entry.setValue` trên một map mutable.
3. **Nguồn → view:** Thực hiện thay đổi hợp lệ ở nguồn rồi kiểm tra view. Với `subList`, ưu tiên thay thế phần tử bằng `set`; không thay đổi cấu trúc list nguồn bên ngoài view đang dùng.
4. **Giới hạn thao tác:** Kiểm tra `UnsupportedOperationException` cho thao tác bị cấm. `Arrays.asList` cho phép `set` nhưng không cho phép `add`; `Collections.unmodifiableList` không cho sửa qua wrapper.
5. **Độc lập của bản sao:** Sau khi copy một nguồn mutable, sửa nguồn rồi xác nhận container copy giữ cấu trúc/nội dung phần tử tại thời điểm copy (trừ khi bản thân phần tử mutable bị thay đổi).
6. **Chia sẻ đối tượng phần tử:** Dùng một đối tượng mutable như `StringBuilder` để kiểm tra copy nông vẫn trỏ đến cùng phần tử.

Mỗi test nên tạo dữ liệu riêng để không phụ thuộc vào thứ tự chạy test. Dùng `LinkedHashMap` nếu muốn kiểm tra một thứ tự duyệt cụ thể; không suy diễn thứ tự từ `HashMap`.

### Cảnh báo đặc biệt với `subList`

Theo hợp đồng `List.subList`, nếu list gốc bị **thay đổi cấu trúc ở bên ngoài view**, ngữ nghĩa của view sau đó **không được xác định**. Ví dụ:

```java
List<String> source = new ArrayList<>(List.of("A", "B", "C"));
List<String> view = source.subList(1, 3);
source.add("D"); // thay đổi cấu trúc trực tiếp ở source
// Không viết assertion về view.get(0) sau dòng này.
```

Một triển khai hiện tại có thể ném `ConcurrentModificationException`, nhưng **không được viết test bắt buộc phải ném ngoại lệ đó** để mô tả hợp đồng. Nếu cần xóa đoạn, gọi `source.subList(from, to).clear()`; nếu cần danh sách con độc lập để sử dụng lâu dài, dùng `new ArrayList<>(source.subList(from, to))`.

## 3. Chương trình tự kiểm tra chạy độc lập (Java 17+)

Lưu thành tệp `AliasingViewChecks.java`. Chương trình dùng những phép kiểm tra đơn giản để dễ chạy khi chưa cài framework test; mỗi điều kiện sai sẽ dừng bằng `AssertionError`. Hàm `expectUoe` chỉ chấp nhận đúng loại ngoại lệ cần kiểm tra, nên không nuốt một lỗi bất kỳ.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AliasingViewChecks {
    private static int checks = 0;

    private static void check(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
        checks++;
    }

    private static void expectUoe(Runnable action, String name) {
        try {
            action.run();
        } catch (UnsupportedOperationException expected) {
            checks++;
            return;
        }
        throw new AssertionError(
                "Expected UnsupportedOperationException: " + name);
    }

    public static void main(String[] args) {
        // 1. Alias: hai biến trỏ đến cùng một ArrayList.
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> alias = source;
        check(alias == source, "same reference");
        alias.set(0, "X");
        check(source.get(0).equals("X"), "alias write");

        // 2. subList: thay thế hai chiều; xóa đoạn qua view.
        List<String> slice = source.subList(1, 3);
        slice.set(0, "Y");
        check(source.get(1).equals("Y"), "subList to source");
        source.set(2, "Z"); // không thay đổi cấu trúc
        check(slice.get(1).equals("Z"), "source to subList");
        slice.clear();
        check(source.equals(List.of("X", "D")), "subList clear");

        // 3. Arrays.asList: backed bởi mảng và fixed-size.
        String[] array = {"red", "blue"};
        List<String> arrayView = Arrays.asList(array);
        arrayView.set(1, "green");
        check(array[1].equals("green"), "list to array");
        array[0] = "black";
        check(arrayView.get(0).equals("black"), "array to list");
        expectUoe(() -> arrayView.add("white"), "fixed size");

        // 4. Unmodifiable wrapper: chỉ đọc qua view, vẫn live.
        List<String> mutable =
                new ArrayList<>(List.of("one", "two"));
        List<String> readOnly =
                Collections.unmodifiableList(mutable);
        mutable.set(0, "ONE");
        check(readOnly.get(0).equals("ONE"), "unmodifiable is live");
        expectUoe(() -> readOnly.set(0, "X"),
                "unmodifiable mutation");

        // 5. List.copyOf: copy không theo thay đổi của list nguồn.
        List<String> copy = List.copyOf(mutable);
        mutable.set(1, "TWO");
        check(copy.equals(List.of("ONE", "two")),
                "independent copy");
        expectUoe(() -> copy.add("three"),
                "copy unmodifiable");

        // 6. Các collection view của Map.
        Map<String, Integer> map = new LinkedHashMap<>();
        map.put("a", 1);
        map.put("b", 2);
        Set<String> keys = map.keySet();
        keys.remove("a");
        check(!map.containsKey("a"), "keySet removal");
        map.put("c", 3);
        check(keys.contains("c"), "keySet live view");
        Collection<Integer> values = map.values();
        values.remove(Integer.valueOf(2));
        check(!map.containsKey("b"), "values removal");
        Map.Entry<String, Integer> entry =
                map.entrySet().iterator().next();
        entry.setValue(30);
        check(map.get("c") == 30, "entry value write");

        // 7. Copy nông: đối tượng phần tử mutable vẫn được chia sẻ.
        List<StringBuilder> objects = new ArrayList<>();
        objects.add(new StringBuilder("start"));
        List<StringBuilder> shallow = List.copyOf(objects);
        objects.get(0).append("-changed");
        check(shallow.get(0).toString().equals("start-changed"),
                "shallow element");

        System.out.println("PASS: " + checks + " checks");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AliasingViewChecks.java
java AliasingViewChecks
```

Kết quả trên JDK hỗ trợ Java 17 trở lên:

```text
PASS: 17 checks
```

Ở đây 17 phép kiểm tra bao phủ cả chia sẻ tham chiếu, backed view, các thao tác bị giới hạn, view của `Map` và aliasing của phần tử. Khi một điều kiện sai, chương trình báo tên trường hợp thất bại thay vì tiếp tục in kết quả thành công.

## 4. Hiểu kết quả và tránh kết luận sai

### `subList` không phải một bản sao

Đoạn `subList(1, 3)` chọn chỉ số 1 (gồm) đến 3 (không gồm). Ban đầu `source = [A, B, C, D]`; sau khi ghi qua alias, nguồn là `[X, B, C, D]`. `slice.set(0, "Y")` làm nguồn thành `[X, Y, C, D]`. `source.set(2, "Z")` làm view thành `[Y, Z]`. Cuối cùng `slice.clear()` bỏ chính hai phần tử đó khỏi nguồn, kết quả `[X, D]`. Các thao tác này nằm trong hợp đồng, vì sự thay đổi cấu trúc (xóa) diễn ra **thông qua view**.

### `Arrays.asList` cố định độ dài nhưng vẫn sửa phần tử được

`Arrays.asList(array)` trả một list có backing array. Nó hỗ trợ `get`/`set` nhưng `add` hay `remove` thay đổi kích thước sẽ ném `UnsupportedOperationException`. Một test chỉ kiểm tra ngoại lệ của `add` mà kết luận list là bất biến là sai: `set` vẫn sửa trực tiếp phần tử mảng.

Với mảng nguyên thủy, `Arrays.asList(new int[]{1, 2})` tạo một `List<int[]>` có **một phần tử**, không phải `List<Integer>` có hai phần tử. Khi cần các phần tử dạng `Integer`, dùng mảng `Integer[]` hoặc chuyển đổi phù hợp.

### Unmodifiable view khác snapshot

`Collections.unmodifiableList(mutable)` chặn các thao tác sửa **đi qua wrapper**. Tuy nhiên nó đọc dữ liệu từ `mutable`, nên người khác còn tham chiếu đến `mutable` có thể cập nhật và kết quả đọc qua wrapper thay đổi theo.

Ngược lại, `List.copyOf(mutable)` trả một list không sửa được và giữ các phần tử của nguồn mutable tại thời điểm tạo bản sao. Không nên assert hai object luôn khác identity với `assertNotSame`: implementation có thể tái sử dụng một collection đã unmodifiable. Chỉ kiểm tra điều ứng dụng thật sự cần, như trạng thái đã copy không bị thay đổi khi sửa nguồn mutable.

**Cả `List.copyOf` và `new ArrayList<>(...)` đều chỉ copy container**, không tự sao chép sâu các phần tử. Ví dụ `StringBuilder` trong chương trình cho thấy trạng thái phần tử vẫn đổi qua một tham chiếu khác. Nếu cần snapshot bất biến về mặt nội dung, hãy chuyển từng phần tử thành giá trị bất biến hoặc tự xây dựng phép sao chép phần tử theo mô hình dữ liệu.

### View của `Map` có thể sửa map

`keySet`, `values` và `entrySet` là các view liên kết với map. Khi map là mutable và hỗ trợ thao tác tương ứng:

- `map.keySet().remove(key)` xóa cả mapping; `map.values().remove(value)` xóa một mapping mang value đó (nếu nhiều key có cùng value, không được giả định key nào bị xóa).
- `map.put(key, value)` có thể được quan sát ngay qua view đã lấy trước đó.
- Với `LinkedHashMap` mutable, `entry.setValue(newValue)` trên entry lấy từ `entrySet()` thay đổi mapping gốc.
- Các view không cung cấp `add` để thêm key/value/entry; muốn thêm mapping hãy dùng `map.put(...)`.

Đừng giữ iterator của một view rồi sửa cấu trúc map bên ngoài iterator và bắt buộc kiểm tra một kết quả cố định; hợp đồng duyệt và fail-fast không bảo đảm điều đó. Chỉ sử dụng `Iterator.remove()` nếu view và iterator hỗ trợ.

## 5. Chuyển các ý tưởng thành unit test JUnit Jupiter

Trong dự án **đã có JUnit Jupiter** trên test classpath, có thể đặt ví dụ sau vào `src/test/java/AliasingViewTest.java`. Đây là test class phụ thuộc JUnit Jupiter, tách biệt với chương trình Java độc lập ở trên.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AliasingViewTest {
    @Test
    void aliasSharesIdentityAndState() {
        List<String> source = new ArrayList<>(List.of("a", "b"));
        List<String> alias = source;

        assertSame(source, alias);
        alias.set(0, "A");
        assertEquals(List.of("A", "b"), source);
    }

    @Test
    void subListReflectsNonStructuralWritesBothWays() {
        List<String> source =
                new ArrayList<>(List.of("a", "b", "c"));
        List<String> view = source.subList(1, 3);

        view.set(0, "B");
        assertEquals(List.of("a", "B", "c"), source);

        source.set(2, "C");
        assertEquals(List.of("B", "C"), view);
    }

    @Test
    void unmodifiableViewRejectsWriteButReflectsSource() {
        List<String> source = new ArrayList<>(List.of("a"));
        List<String> view = Collections.unmodifiableList(source);

        assertThrows(UnsupportedOperationException.class,
                () -> view.add("b"));
        source.add("b");
        assertEquals(List.of("a", "b"), view);
    }

    @Test
    void defensiveCopyDoesNotFollowSourceMutation() {
        List<String> source = new ArrayList<>(List.of("a"));
        List<String> snapshot = List.copyOf(source);

        source.set(0, "A");
        assertEquals(List.of("a"), snapshot);
        assertThrows(UnsupportedOperationException.class,
                () -> snapshot.set(0, "B"));
    }
}
```

Cách chọn assertion:

- `assertSame` dùng cho **alias thực sự cùng đối tượng**; `assertEquals` dùng để so sánh trạng thái quan sát được. Hai view có nội dung bằng nhau không chứng minh chúng là cùng một object.
- `assertThrows(UnsupportedOperationException.class, ...)` dùng cho thao tác mà tài liệu API quy định không được hỗ trợ. Không dùng nó để giả định mọi thao tác sửa đều bị cấm trên `Arrays.asList`.
- Với backed view, phải kiểm thử **giá trị sau thao tác**; chỉ kiểm tra kiểu class hoặc `toString()` là không đủ.
- Với `subList`, đừng thay đổi cấu trúc list gốc trực tiếp giữa lúc lấy view và lúc đọc view, vì test sẽ phụ thuộc vào hành vi không xác định.

## 6. Những lỗi thường gặp khi kiểm thử và thiết kế API

**Lỗi 1: Test bằng `equals` rồi kết luận không alias.** Hai list độc lập có thể đang bằng nhau; ngược lại hai biến trỏ một list luôn thấy cùng trạng thái. Muốn chứng minh tách trạng thái, hãy tạo bản sao, sửa một bên và kiểm tra bên còn lại.

**Lỗi 2: Gọi `Collections.unmodifiableList` để có snapshot.** Đây là live view, không phải một bản sao độc lập. Nếu cần danh sách không sửa được tách khỏi một nguồn mutable, dùng `List.copyOf(source)` (khi không có phần tử `null`). Nếu vẫn cần một bản sao mutable, dùng `new ArrayList<>(source)`.

**Lỗi 3: Coi `Arrays.asList` là một `ArrayList` kích thước tùy biến.** Ghi `set` hợp lệ nhưng thao tác thay đổi kích thước không hợp lệ. Tên lớp triển khai bên trong JDK không phải thứ nên đem ra assert.

**Lỗi 4: Đọc `subList` sau khi gọi `source.add/remove` bên ngoài view.** Khi nguồn thay đổi cấu trúc theo cách đó, view có ngữ nghĩa không xác định. Tránh vừa thay nguồn vừa giữ view lâu dài; tạo bản sao khi cần.

**Lỗi 5: Giả định unmodifiable nghĩa là deep immutable.** Wrapper chỉ hạn chế thao tác qua wrapper; bản sao nông vẫn dùng chung object phần tử. Test thêm một đối tượng mutable để phát hiện sự chia sẻ ngoài ý muốn.

**Lỗi 6: Dùng `ConcurrentModificationException` như một bảo đảm.** Cơ chế fail-fast chỉ là nỗ lực phát hiện thay đổi đồng thời/ngoài iterator; đừng lấy việc có hay không ngoại lệ này làm hợp đồng đúng sai của backed view.

**Lỗi 7: Bỏ qua ranh giới luồng.** Backed view không tự khiến collection nền an toàn khi truy cập đồng thời. Unmodifiable wrapper cũng không tự đồng bộ hóa các thay đổi xảy ra qua nguồn. Khi có nhiều luồng, lựa chọn chiến lược đồng bộ hoặc cấu trúc dữ liệu phù hợp riêng; không dùng các test một luồng để suy ra thread safety.

## 7. Khi nào chọn view, khi nào chọn bản sao?

Nếu một hàm **cần quan sát thay đổi hiện tại từ nguồn**, view có thể phù hợp, miễn là vòng đời và quyền sửa được quản lý rõ ràng. Nếu một hàm **không được ảnh hưởng hay bị ảnh hưởng bởi thao tác sửa cấu trúc từ bên ngoài**, thường cần defensive copy.

```java
List<String> source = new ArrayList<>(List.of("a", "b"));

List<String> liveReadOnly = Collections.unmodifiableList(source);
// Không thể sửa qua liveReadOnly, nhưng source đổi thì view có thể đổi.

List<String> mutableCopy = new ArrayList<>(source);
// Container mới, có thể sửa và không theo thay đổi cấu trúc của source.

List<String> fixedSnapshot = List.copyOf(source);
// Container không sửa được, không theo thay đổi cấu trúc của source.
// Yêu cầu các phần tử đầu vào khác null (Java 10+).
```

Có thể đặt câu hỏi trước khi viết test: **Ai sở hữu dữ liệu nền? Ai được sửa? Thay đổi cần thấy ở đâu? Snapshot có cần sâu đến từng phần tử không?** Đáp án sẽ quyết định chọn view hay copy và những assertion nào có ý nghĩa.

## 8. Bài tự kiểm tra ngắn

1. Một list tạo bằng `Arrays.asList(String[])` bị thay đổi qua `set(0, "x")`. Mảng nguồn có đổi không? **Có**, vì list được mảng chống lưng. `add` vào list đó thì sao? **Ném `UnsupportedOperationException`**, do thay đổi kích thước.
2. `Collections.unmodifiableList(original)` có giữ nguyên giá trị nếu `original.set(0, "new")` không? **Không**; wrapper vẫn đọc dữ liệu của nguồn.
3. Tạo `List.copyOf(source)` từ một `ArrayList<String>` mutable rồi `source.set(0, "new")`. Bản sao có đổi không? **Không** đối với container của các `String` đã copy. Nếu phần tử là `StringBuilder` mutable và bị sửa nội dung qua tham chiếu khác thì bản sao có thể quan sát thay đổi vì copy nông.
4. Sau khi tạo `subList`, gọi `source.add(...)` rồi test phải nhận `ConcurrentModificationException` có đúng không? **Không**: khi thay đổi cấu trúc nguồn bên ngoài view, hành vi của view không được xác định; không được gắn test với ngoại lệ cụ thể.

## Tài liệu API hiện hành

- [`List.subList`, `List.of` và `List.copyOf` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [`Arrays.asList` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html)
- [`Collections.unmodifiableList` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html)
- [`Map` và các collection view — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)

Các đường dẫn dùng Javadoc hiện hành để xác minh hợp đồng API. Những hành vi trong bài (aliasing, backed view, copy nông, giới hạn mutator) vẫn có giá trị với Java hiện đại; không dựa vào API đã lỗi thời hay chi tiết nội bộ của một bản JDK.
