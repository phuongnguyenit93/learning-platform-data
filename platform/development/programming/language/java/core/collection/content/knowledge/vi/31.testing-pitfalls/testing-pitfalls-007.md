# ClassCastException, NullPointerException và kiểu dữ liệu không hợp lệ trong Java Collections

## 1. Mục tiêu

Trong Java Collections (`List`, `Set`, `Queue`, `Map`), lỗi có thể xuất hiện lúc thêm, đọc, sắp xếp, chuyển đổi hoặc sử dụng phần tử. Cần phân biệt ba nhóm:

- **`ClassCastException`**: một đối tượng bị ép sang kiểu mà đối tượng thực tế không thuộc về. Với generic, lỗi có thể phát sinh tại `get()` do trình biên dịch chèn phép ép kiểu ngầm.
- **`NullPointerException` (NPE)**: dereference `null`, tự động unboxing giá trị `null` hoặc truyền null vào factory/API không chấp nhận null.
- **Kiểu/giá trị không hợp lệ**: dữ liệu bên ngoài vi phạm hợp đồng kiểu hoặc quy tắc nghiệp vụ (ví dụ nhận chuỗi `"90"` ở nơi cần `Integer`, hoặc điểm số `120` ở nơi chỉ nhận 0–100).

Mục tiêu là xác định điểm gây lỗi, phòng tránh bằng generic và validation, đồng thời kiểm thử cả luồng đúng và luồng sai trên Java 17+.

## 2. Nhận diện đúng loại lỗi

| Hiện tượng | Exception | Giải thích |
| --- | --- | --- |
| Đọc `String` nhưng phần tử thực là `Integer` | `ClassCastException` | Cast sai; thường do raw type/unchecked cast làm ô nhiễm kiểu trong collection. |
| Gọi phương thức trên phần tử `null` | `NullPointerException` | `null` không phải đối tượng để dereference. |
| Lấy `Integer` null rồi gán vào `int` | `NullPointerException` | Unboxing cần giá trị không null. |
| Tạo `List.of("A", null)`, `List.copyOf` có null | `NullPointerException` | Các factory này cấm phần tử null. |
| Dữ liệu đúng kiểu nhưng ngoài miền chấp nhận | `IllegalArgumentException` nếu chủ động validate | Đây là lỗi hợp đồng dữ liệu, không phải ép kiểu. |
| Parse `"12x"` thành số nguyên | `NumberFormatException` | Chuỗi không đúng dạng số, khác với cast từ `String` sang `Integer`. |
| Copy phần tử `Integer` vào `String[]` qua `toArray(T[])` | `ArrayStoreException` | Mảng đích có kiểu thành phần không tương thích. |
| Thêm vào `List.of` hoặc `List.copyOf` | `UnsupportedOperationException` | Kết quả không sửa đổi được; không liên quan đến kiểu phần tử. |
| Đọc chỉ số ngoài kích thước danh sách | `IndexOutOfBoundsException` | Lỗi biên chỉ số, không phải NPE hoặc ClassCastException. |

Tên exception cho biết triệu chứng tại một thao tác cụ thể; vị trí dữ liệu sai đi vào hệ thống có thể ở một dòng khác. Không bắt mọi `RuntimeException` rồi trả về giá trị mặc định: điều đó dễ che mất lỗi dữ liệu.

## 3. ClassCastException và generic

### 3.1. Vì sao generic vẫn có thể lỗi lúc chạy?

`List<String>` giúp trình biên dịch từ chối `names.add(42)` nếu `names` được khai báo đúng kiểu. Nhưng Java sử dụng **type erasure**: phần lớn tham số generic không được giữ để kiểm tra tự động từng phần tử ở runtime. Raw type, cast không kiểm tra (`unchecked cast`), reflection hay một thư viện cũ có thể đưa sai kiểu vào danh sách.

```java
List<String> names = new ArrayList<>();
List raw = names;         // Raw type: mất kiểm tra generic.
raw.add(42);             // Chèn Integer vào List<String>.
String first = names.get(0); // ClassCastException tại điểm đọc.
```

Đoạn trên cần import `java.util.ArrayList` và `java.util.List`; trình biên dịch cảnh báo về raw/unchecked operation. Không dùng cách này trong production. Phần tử sai đã được chèn trước khi exception xuất hiện; sửa dòng `get` mà không sửa điểm `add` chỉ chữa triệu chứng.

Không thể viết `value instanceof List<String>`: tham số `String` bị xóa. `value instanceof List<?>` chỉ xác nhận đối tượng là `List`; muốn tin rằng mọi phần tử là `String`, phải kiểm tra các phần tử hoặc nhận collection từ nguồn có hợp đồng kiểu đáng tin cậy.

### 3.2. Chạy một bài lab tái hiện lỗi

Lưu thành tệp `CollectionFailureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionFailureDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> pollutedList() {
        List<String> names = new ArrayList<>();
        List raw = names;
        raw.add(42); // Cố ý sai để mô phỏng API cũ.
        return names;
    }

    static void show(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": OK");
        } catch (RuntimeException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("wrong-cast", () -> {
            String name = pollutedList().get(0);
            System.out.println(name);
        });

        show("null-element", () -> {
            List<String> names = new ArrayList<>();
            names.add(null);
            System.out.println(names.get(0).length());
        });

        show("factory-null", () -> {
            List.of("An", null);
        });

        show("null-unboxing", () -> {
            List<Integer> values = new ArrayList<>();
            values.add(null);
            int number = values.get(0);
            System.out.println(number);
        });
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac CollectionFailureDemo.java
java CollectionFailureDemo
```

Stdout:

```text
wrong-cast: ClassCastException
null-element: NullPointerException
factory-null: NullPointerException
null-unboxing: NullPointerException
```

`@SuppressWarnings` chỉ được dùng trong ví dụ mô phỏng mã không an toàn; nó không kiểm tra hoặc sửa nội dung collection. Hàm `show` bắt exception để minh họa; ứng dụng thật nên để lỗi bất ngờ được báo rõ hoặc chuyển sang lỗi có ngữ cảnh tại ranh giới phù hợp.

### 3.3. Cách tránh ép kiểu sai

Với một giá trị `Object` đến từ nguồn không đáng tin cậy:

```java
Object value = 42;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String");
}
```

Kết quả: `Không phải String`. `instanceof` với `null` cho kết quả `false`. Tuy nhiên, nếu hợp đồng yêu cầu *mọi* phần tử đều là `String`, chỉ im lặng bỏ qua phần tử sai sẽ làm mất dữ liệu. Tốt hơn là validate toàn bộ đầu vào, chỉ rõ chỉ số và loại giá trị sai, rồi trả về collection đã được chuẩn hóa.

`Collections.checkedList(new ArrayList<String>(), String.class)` có thể bảo vệ một ranh giới với raw API: wrapper kiểm tra kiểu khi thêm và có thể ném `ClassCastException` sớm. Wrapper **không tự quét và sửa** các phần tử sai vốn đã có trong danh sách gốc. Generic đúng và validation ở đầu vào vẫn là biện pháp chính.

### 3.4. Sorted collections cũng có hợp đồng kiểu

`TreeSet`/`TreeMap` phải so sánh các phần tử/khóa. Nếu dùng thứ tự tự nhiên, các giá trị cần hỗ trợ so sánh tương thích; nếu dùng `Comparator`, comparator phải nhận đúng kiểu và tạo thứ tự nhất quán. Trộn các kiểu không tương thích qua raw collection có thể gây `ClassCastException` khi thêm, tìm hoặc sắp xếp, tùy dữ liệu và thao tác.

Dùng `TreeSet<String>` hoặc comparator khai báo kiểu rõ ràng. Nếu cần so sánh với null, xác định quy tắc bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)` kết hợp comparator thích hợp. Không giả định thứ tự tự nhiên chấp nhận null.

## 4. NullPointerException trong các thao tác collection

### 4.1. Chính sách null thay đổi theo API

- `ArrayList` có thể chứa phần tử null; `HashMap` cho phép một khóa null và các giá trị null.
- `List.of(...)`, `Set.of(...)`, `Map.of(...)`, `List.copyOf(...)` từ chối các null không được phép; lỗi thường xảy ra ngay khi tạo.
- `ConcurrentHashMap` không cho khóa/giá trị null.
- `TreeMap` với thứ tự khóa tự nhiên không cho khóa null; với comparator riêng, khả năng xử lý null phụ thuộc comparator.
- `Collections.unmodifiableList(list)` chỉ tạo view ngăn sửa qua wrapper; nó không tự loại bỏ null đã có trong danh sách nguồn.

Ví dụ:

```java
List<String> names = new ArrayList<>();
names.add(null);                    // Hợp lệ.
System.out.println(names.size()); // 1
System.out.println(names.get(0)); // null
names.get(0).length();            // NullPointerException.
```

`null` có thể được chèn hợp lệ nhưng gây NPE ở lần dùng sau. Tương tự, `Integer boxed = null; int n = boxed;` ném NPE vì Java phải gọi quá trình unboxing.

### 4.2. Map.get trả về null chưa đủ để kết luận thiếu khóa

Với `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, String> labels = new HashMap<>();
labels.put("has-null", null);

System.out.println(labels.containsKey("has-null")); // true
System.out.println(labels.containsKey("missing"));  // false
System.out.println(labels.get("has-null"));         // null
System.out.println(labels.get("missing"));          // null
```

`get(key) == null` không phân biệt được khóa vắng mặt và khóa có mapping đến null. `getOrDefault(key, fallback)` chỉ trả fallback khi không có mapping; mapping hiện có với giá trị null vẫn có thể khiến kết quả là null. Hãy quyết định rõ nghiệp vụ có cần phân biệt hai trạng thái này không, rồi dùng `containsKey` hoặc thay đổi mô hình dữ liệu cho phù hợp.

### 4.3. Thiết lập hợp đồng null ngay tại ranh giới

Nếu toàn bộ tham số không được phép null, dùng `Objects.requireNonNull(input, "input")` để ném lỗi sớm và rõ tên tham số. Nếu **phần tử** có thể null, phải có chính sách: từ chối, lọc có chủ đích, hoặc dùng giá trị thay thế được nghiệp vụ chấp nhận. Không tự chuyển `null` thành `0` hay chuỗi rỗng chỉ để tránh exception nếu chúng có nghĩa khác nhau.

Sau khi validation xác nhận không có null, `List.copyOf` là một lựa chọn để trả về danh sách không sửa đổi được. `Optional` có thể phù hợp với một API trả về *một giá trị tùy chọn*, nhưng bọc tràn lan mọi phần tử của collection vào `Optional` không giải quyết hợp đồng dữ liệu chưa rõ.

## 5. Kiểu dữ liệu không hợp lệ: validate thay vì cast

### 5.1. Phân biệt sai kiểu và sai miền giá trị

Một API nhận điểm số `Integer` trong khoảng 0–100 có thể gặp:

- `"90"`: kiểu Java là `String`, không thể cast trực tiếp thành `Integer`. Nếu cho phép nhập chuỗi, phải parse bằng `Integer.parseInt` và xử lý `NumberFormatException` khi định dạng sai.
- `null`: không có giá trị; cần chính sách null.
- `120`: đúng kiểu `Integer` nhưng sai miền; có thể ném `IllegalArgumentException` với thông tin chỉ số và khoảng hợp lệ.

Đừng trộn validation với cast unchecked. Khi dữ liệu đến từ CSV/JSON/API cũ, có thể nhận `Collection<?>` ở biên ngoài, kiểm tra từng phần tử, sau đó chỉ chuyển collection đã xác thực cho tầng nghiệp vụ.

### 5.2. Ví dụ validation đầy đủ kèm test

Lưu thành `CollectionValidationLab.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

public class CollectionValidationLab {
    static List<Integer> validatedScores(Collection<?> input) {
        Objects.requireNonNull(input, "input");
        List<Integer> result = new ArrayList<>();

        int index = 0;
        for (Object item : input) {
            if (!(item instanceof Integer score)) {
                String actual = item == null
                        ? "null"
                        : item.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "index " + index + ": expected Integer, got " + actual);
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException(
                        "index " + index + ": outside 0..100");
            }
            result.add(score);
            index++;
        }
        return List.copyOf(result);
    }

    static void expect(Class<? extends RuntimeException> expected,
                       Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (expected.isInstance(ex)) {
                return;
            }
            throw new AssertionError(
                    "Expected " + expected.getSimpleName()
                            + " but got " + ex, ex);
        }
        throw new AssertionError(
                "Expected " + expected.getSimpleName() + " but no exception");
    }

    public static void main(String[] args) {
        List<Integer> good = validatedScores(Arrays.asList(80, 90));
        if (!good.equals(List.of(80, 90))) {
            throw new AssertionError("Wrong values");
        }

        expect(NullPointerException.class,
                () -> validatedScores(null));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, null)));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, "90")));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, 101)));
        expect(UnsupportedOperationException.class,
                () -> good.add(95));

        System.out.println("6 checks passed");
    }
}
```

Chạy với JDK 17+:

```bash
javac CollectionValidationLab.java
java CollectionValidationLab
```

Stdout chính xác nếu mọi check đạt:

```text
6 checks passed
```

Một lần kiểm tra danh sách hợp lệ và năm lần `expect` tạo thành sáu check. Phương thức không tin kiểu phần tử từ đầu vào `Collection<?>`; nó xác nhận đúng `Integer`, loại bỏ null và số ngoài 0–100 bằng lỗi rõ ràng, rồi trả về `List<Integer>` bất biến theo giao diện. Null của **toàn collection** được coi là lỗi tham số bắt buộc (NPE); null của **phần tử** được coi là lỗi dữ liệu (IllegalArgumentException). Đó là một hợp đồng đã chọn nhất quán, có thể thay bằng loại exception miền nghiệp vụ khác nếu dự án quy định.

`expect` không chấp nhận exception bất kỳ: sai loại hoặc không có exception đều dẫn đến `AssertionError`. Việc chỉ gọi hàm trong `try/catch` và không assert gì sẽ dễ tạo test “xanh giả”. Không nên bắt `RuntimeException` chung trong logic nghiệp vụ rồi âm thầm tiếp tục.

**Mở rộng quan trọng:** ví dụ từ chối chuỗi `"90"` thay vì tự ý parse. Nếu hệ thống cần hỗ trợ chuỗi, hãy bổ sung yêu cầu vào hợp đồng và test cả `"90"`, `""`, `"90x"`, chuỗi có khoảng trắng, số âm, số vượt miền, và vấn đề định dạng. Đừng biến dữ liệu không hợp lệ thành dữ liệu hợp lệ theo phỏng đoán.

## 6. Những lỗi kiểu liên quan dễ nhầm

**ArrayStoreException với `toArray`:** lời gọi `List.of(1, 2).toArray(new String[0])` có thể biên dịch vì chữ ký generic của `toArray(T[])`, nhưng lỗi runtime khi sao chép `Integer` vào `String[]`. Dùng `toArray(new Integer[0])` hoặc `toArray(Integer[]::new)`.

**ClassCastException trong comparator:** một collection sắp xếp đã trộn kiểu qua raw reference có thể ném lỗi ở chỗ so sánh, thay vì chỗ thêm phần tử ban đầu. Dùng comparator cùng kiểu với element/key, kiểm tra null và quy tắc thứ tự.

**UnsupportedOperationException với factory bất biến:** `List.of("A").add("B")` ném lỗi vì không cho sửa. Đừng diễn giải thành kiểu phần tử không hợp lệ. `List.copyOf` từ chối null và không cho sửa; đó là hai hợp đồng khác nhau.

**ClassCastException không phải NumberFormatException:** `(Integer) (Object) "123"` là ép kiểu sai; `Integer.parseInt("123x")` là parse thất bại. Hướng sửa hoàn toàn khác nhau.

## 7. Ma trận kiểm thử nên có

| Kịch bản | Kỳ vọng |
| --- | --- |
| `[80, 90]` | Trả đúng phần tử, kiểu và thứ tự. |
| `[]` | Theo hợp đồng: ví dụ `validatedScores` cho phép và trả danh sách rỗng. |
| `null` là collection đầu vào | Lỗi tham số rõ ràng; ví dụ dùng NPE. |
| `[80, null]` | Từ chối null ở index 1. |
| `[80, "90"]` | Từ chối kiểu `String` dù nội dung trông như số. |
| `[80, 101]` | Từ chối số ngoài miền. |
| `good.add(95)` | `UnsupportedOperationException` nếu kết quả không cho sửa. |
| Raw `List<String>` chứa `Integer` | Tái hiện CCE tại điểm đọc và xác định điểm thêm sai. |
| `Map` có khóa trỏ tới null / khóa không tồn tại | Dùng `containsKey` khi cần phân biệt. |
| `toArray(new String[0])` từ danh sách `Integer` | `ArrayStoreException` với dữ liệu không tương thích. |

Trong dự án cấu hình JUnit 5/JUnit Jupiter, test exception và thông báo lỗi được viết chẳng hạn như sau (đây là file test riêng, không tự chạy chỉ với `javac` nếu chưa có JUnit trong classpath):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Arrays;
import org.junit.jupiter.api.Test;

class CollectionValidationLabTest {
    @Test
    void rejectsNullElementAtCorrectIndex() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> CollectionValidationLab.validatedScores(
                        Arrays.asList(80, null)));
        assertEquals("index 1: expected Integer, got null", ex.getMessage());
    }
}
```

Đặt test cùng package với `CollectionValidationLab`, hoặc điều chỉnh visibility theo cấu trúc dự án. Với thông báo NPE do JVM tự tạo, không nên phụ thuộc nguyên văn vào một biến thể thông báo có thể đổi theo phiên bản/runtime; hãy assert loại lỗi và hợp đồng do API của mình định nghĩa.

## 8. Quy trình debug và phòng ngừa

1. **Đọc exception và stack trace đầu tiên.** Ghi nhận thao tác: `get`, cast, sort, lookup, dereference, unboxing, factory hay `toArray`.
2. **Kiểm tra dữ liệu ở điểm lỗi.** Với giá trị khác null, `value.getClass().getName()` giúp biết runtime type; luôn kiểm tra null trước khi gọi `getClass()`. Trong log chỉ ghi thông tin được phép, tránh lộ dữ liệu nhạy cảm.
3. **Lần ngược đến điểm dữ liệu đi vào.** CCE ở `get` thường bắt nguồn từ raw `add`, adapter hoặc cast unchecked. NPE ở lần gọi phương thức thường do null được trả về ở thao tác trước.
4. **Đối chiếu hợp đồng.** Null có được phép? Collection nào cho null? Kiểu và miền giá trị nào hợp lệ? `Map.get` thiếu khóa có bình thường không? Có được sửa collection kết quả không?
5. **Sửa ở ranh giới sớm.** Khai báo generic đúng; validate/parsing tường minh; trả lỗi có vị trí và nguyên nhân; tạo collection đã kiểm tra để các tầng sau không phải cast lại.
6. **Thêm regression test.** Kiểm tra cả đầu vào hợp lệ, null, sai kiểu, sai miền, rỗng, mảng đích sai kiểu, và hành vi khi kết quả không cho sửa.

Không coi việc bỏ qua phần tử sai, thay `null` bằng `0` hoặc bắt mọi exception rồi trả danh sách rỗng là giải pháp mặc định. Chúng có thể che giấu việc mất dữ liệu. Nếu chuyển ngoại lệ sang một lỗi ở tầng cao, nên giữ cause (ví dụ `new IllegalArgumentException("Invalid scores", ex)`).

## 9. Checklist trước khi giao code

- Có generic rõ ràng trên collection và tránh raw type/unchecked cast không kiểm soát.
- Hợp đồng quy định null cho collection, từng phần tử và khóa/giá trị map.
- Dữ liệu ngoài được validate về kiểu **và** miền giá trị trước khi dùng.
- Không dùng cast để parse chuỗi, không nhầm CCE với `NumberFormatException` hay `IllegalArgumentException`.
- Collection sắp xếp có comparator đúng kiểu, chính sách null và thứ tự nhất quán.
- Test khẳng định đúng exception, dữ liệu, vị trí lỗi và trạng thái sửa đổi; có regression test cho lỗi từng gặp.
- Nếu exception xuất hiện ở **điểm đọc**, vẫn tìm nguyên nhân tại **điểm ghi**.

**Kết luận:** Generic loại bỏ nhiều lỗi ở thời điểm biên dịch; collection nhận dữ liệu không đáng tin vẫn cần validation runtime. Hợp đồng null/kiểu rõ ràng, kiểm tra sớm và test có chủ đích là cách ngăn `ClassCastException` và `NullPointerException` tái xuất hiện trong những luồng nghiệp vụ phức tạp.