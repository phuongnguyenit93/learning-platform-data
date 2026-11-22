# Phân biệt `List<Object>`, `List<?>` và raw `List`

Trong Java Generics, cả ba khai báo đều liên quan đến `java.util.List`, nhưng chúng diễn tả **ba hợp đồng kiểu khác nhau**. Điểm mấu chốt là phân biệt: (1) danh sách được khai báo chứa phần tử kiểu `Object`; (2) danh sách có kiểu phần tử **chưa biết**; và (3) danh sách đã **bỏ qua kiểm tra tham số kiểu**. Nhìn ba khai báo giống nhau về hình dáng không có nghĩa chúng có cùng mức độ an toàn.

## 1. Ba khai báo có ý nghĩa gì?

```java
List<Object> objects; // Danh sách có kiểu phần tử chính xác là Object
List<?> unknown;       // Danh sách có một kiểu phần tử nào đó, chưa biết kiểu nào
List raw;              // Raw type: không khai báo tham số kiểu của List<E>
```

- **`List<Object>`**: `E` là `Object`. Ta có thể đưa vào phần tử `String`, `Integer` hoặc một đối tượng khác vì tất cả đều là đối tượng có thể gán cho `Object`. Khi đọc, kiểu tĩnh trả về là `Object`.
- **`List<?>`**: có một tham số kiểu thực sự, nhưng mã đang sử dụng danh sách **không biết** tham số đó là `String`, `Integer` hay kiểu nào khác. Ký hiệu `?` là *unbounded wildcard*. Khi đọc một phần tử, kết quả an toàn nhất là `Object`; khi thêm phần tử thông thường, trình biên dịch phải từ chối vì không biết phần tử có hợp kiểu hay không.
- **Raw `List`**: cách viết không có `<...>`, chủ yếu tồn tại để tương thích với mã có trước Generics. Trình biên dịch cho phép nhiều lời gọi thao tác với `Object` mà không bảo vệ tham số kiểu; thao tác không an toàn thường tạo cảnh báo `unchecked`. Đây **không phải** cách biểu diễn tương đương với `List<?>`.

`Object` trong `List<Object>` là **một kiểu cụ thể**, còn `?` trong `List<?>` là **một kiểu chưa biết**. Sự khác nhau này quyết định các phép gán và thao tác nào được phép.

## 2. Vì sao `List<String>` không phải là `List<Object>`?

Giả sử có một danh sách chỉ dành cho chuỗi:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

Dù `String` là kiểu con của `Object`, Java Generics **bất biến** (*invariant*): từ `String extends Object` không thể suy ra `List<String> extends List<Object>`. Đoạn sau cố ý không biên dịch:

```java
List<String> names = new ArrayList<>();
List<Object> objects = names; // LỖI BIÊN DỊCH: incompatible types
objects.add(123);             // Nếu được phép, danh sách String sẽ chứa Integer!
```

Nếu phép gán ấy hợp lệ, một người dùng `objects` có thể thêm `Integer` và làm hỏng cam kết của người dùng `names`. Tính bất biến ngăn chuyện này ngay từ lúc biên dịch.

Có hai lựa chọn hợp lệ nhưng mang ý nghĩa khác nhau:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

List<?> view = names;                       // Cùng đối tượng List, chỉ nhìn qua wildcard
List<Object> copy = new ArrayList<>(names); // Tạo một List<Object> MỚI, chứa bản sao phần tử
copy.add(123);                              // Hợp lệ, không làm thay đổi names
```

Constructor `ArrayList(Collection<? extends E>)` cho phép sao chép phần tử `String` vào một `ArrayList<Object>` mới. Khác với `view`, `copy` **không phải alias** của danh sách gốc; cả hai vẫn có thể chứa tham chiếu đến cùng đối tượng phần tử nếu phần tử là đối tượng mutable.

## 3. So sánh phép gán, đọc và ghi

| Câu hỏi | `List<Object>` | `List<?>` | Raw `List` |
|---|---|---|---|
| Gán trực tiếp một biến `List<String>` vào? | **Không**; Generics bất biến | **Có** | **Có**, nhưng mất thông tin tham số kiểu |
| Kiểu tĩnh khi gọi `get(0)`? | `Object` | `Object` | `Object` |
| `add("text")` hoặc `add(123)`? | **Có** | **Không** | **Có**, thao tác raw không an toàn có thể bị cảnh báo `unchecked` |
| `add(null)`? | Có | Có | Có |
| `set(0, "text")`? | Có | Không | Có, có thể bị cảnh báo |
| Ngăn ghi sai kiểu cho danh sách được tham chiếu? | Có, theo kiểu `Object` của chính danh sách | Có, đối với giá trị phần tử chưa biết kiểu | **Không** |
| Mục đích phù hợp | Cần lưu nhiều loại đối tượng trong một danh sách | Chỉ cần xử lý một danh sách bất kỳ mà không phụ thuộc loại phần tử | Tương tác mã/API cũ chưa khai báo Generics |

**Lưu ý quan trọng:** hạn chế `add` / `set` của `List<?>` **không đồng nghĩa danh sách hoàn toàn bất biến**. Những thao tác không cần cung cấp giá trị kiểu `E` như `clear()`, `remove(Object)` hoặc `remove(int)` vẫn có thể làm thay đổi danh sách. `add(null)` được phép ở mức kiểm tra kiểu vì `null` có thể gán cho mọi kiểu tham chiếu; tuy vậy danh sách bất biến do `List.of(...)` hay `Collections.unmodifiableList(...)` tạo ra vẫn có thể ném `UnsupportedOperationException` khi gọi phương thức sửa đổi. Hãy phân biệt **khả năng biên dịch theo kiểu** và **khả năng sửa đổi thực tế của đối tượng**.

## 4. Ví dụ Java 17 chạy được: raw type phá vỡ hợp đồng như thế nào?

Tạo tệp `ListTypeRelationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ListTypeRelationsDemo {
    public static void main(String[] args) {
        List<Object> objects = new ArrayList<>();
        objects.add("Java");
        objects.add(17);
        System.out.println("Objects: " + objects);

        List<String> words = new ArrayList<>(List.of("alpha", "beta"));

        List<?> unknown = words;
        Object first = unknown.get(0);
        System.out.println("Unknown first: " + first);
        unknown.add(null);
        System.out.println("Unknown after null: " + words);

        List raw = words;
        raw.set(1, 99);
        System.out.println("Raw second: " + raw.get(1));

        try {
            String second = words.get(1);
            System.out.println("Typed second: " + second);
        } catch (ClassCastException ex) {
            System.out.println("Typed second: ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:rawtypes,unchecked ListTypeRelationsDemo.java
java ListTypeRelationsDemo
```

**Stdout** (không bao gồm cảnh báo biên dịch trên stderr):

```text
Objects: [Java, 17]
Unknown first: alpha
Unknown after null: [alpha, beta, null]
Raw second: 99
Typed second: ClassCastException
```

Diễn giải từng bước:

1. `objects` là `List<Object>`: cả `String` và `Integer` đều phù hợp với `Object`; không có vi phạm hợp đồng kiểu.
2. `unknown` là `List<?>` cùng trỏ tới `words`. Đọc được phần tử dưới kiểu `Object`, nhưng **không thể** viết `unknown.add(99)` hay `unknown.add("gamma")` vì kiểu phần tử thật là điều chưa biết. `unknown.add(null)` biên dịch được và ở đây `ArrayList` cho phép thêm.
3. `raw` cũng trỏ tới **chính `words`**. `raw.set(1, 99)` qua mặt kiểm tra tham số `String`, khiến danh sách thực tế chứa `Integer` ở vị trí thứ hai. Khi `words.get(1)` được gán cho `String`, compiler đã chèn phép ép kiểu thích hợp; tại thời điểm chạy việc chuyển `Integer` thành `String` thất bại và ném `ClassCastException`.
4. Với `-Xlint:rawtypes,unchecked`, `javac` cảnh báo nơi dùng raw type và lời gọi không được kiểm tra. Số dòng, nội dung cảnh báo phụ thuộc phiên bản và vị trí mã; cảnh báo **không ngăn chương trình chạy** nếu không bật cơ chế coi cảnh báo là lỗi.

Điều nguy hiểm của raw type là lỗi có thể xuất hiện **muộn** ở một vị trí đọc khác hẳn nơi ghi sai. Hiện tượng dữ liệu bên trong một cấu trúc generic không còn đáp ứng tham số kiểu đã cam kết được gọi là *heap pollution*. Raw type là một nguồn thường gặp của vấn đề này.

## 5. `List<?>` bảo vệ cái gì và giới hạn đến đâu?

Khi viết `List<?> values = someList;`, ta chấp nhận rằng `values` có thể đang tham chiếu `List<String>`, `List<Integer>` hoặc một `List<E>` bất kỳ. Vì vậy:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
List<?> values = numbers;

Object value = values.get(0); // Hợp lệ: đọc được dưới kiểu Object
int count = values.size();     // Hợp lệ: không phụ thuộc E
boolean hasTen = values.contains(10); // Hợp lệ: contains nhận Object

// values.add(30);        // Không biên dịch
// values.set(0, 30);     // Không biên dịch
values.add(null);        // Hợp lệ về kiểu, nhưng làm thay đổi numbers
```

Tại sao `values.add(30)` bị từ chối dù ví dụ này biết `numbers` là `List<Integer>`? Vì compiler xét **kiểu tĩnh `List<?>` của biến `values`**. Phương thức chấp nhận phần tử kiểu ẩn bên trong dấu `?`, trong khi `30` chỉ được chứng minh là `Integer`, không được chứng minh phù hợp với mọi kiểu ẩn có thể có.

Không thể “đổi dấu hỏi thành Object” chỉ để thêm giá trị:

```java
List<?> wildcard = new ArrayList<String>();
// List<Object> wrong = wildcard; // LỖI BIÊN DỊCH
```

Giá trị `wildcard.get(0)` có kiểu `Object` chỉ có nghĩa mọi phần tử đọc được đều là đối tượng; nó **không** làm cho kiểu phần tử mà danh sách chấp nhận trở thành `Object`.

### Wildcard capture: thay đổi an toàn khi giữ nguyên kiểu phần tử

Có trường hợp cần hoán đổi các phần tử hiện có mà không chèn một giá trị từ ngoài vào. Ta có thể dùng một phương thức generic phụ để compiler “bắt” kiểu ẩn của `?` thành `T`.

Tệp `WildcardCaptureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    public static void main(String[] args) {
        List<String> labels = new ArrayList<>(List.of("first", "second"));
        swapFirstTwo(labels);
        System.out.println(labels);
    }

    static void swapFirstTwo(List<?> input) {
        swapCaptured(input);
    }

    private static <T> void swapCaptured(List<T> items) {
        if (items.size() < 2) {
            return;
        }
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }
}
```

Chạy `javac WildcardCaptureDemo.java` rồi `java WildcardCaptureDemo`, stdout:

```text
[second, first]
```

Ở hàm `swapCaptured`, cả giá trị đọc và vị trí ghi đều có cùng một kiểu `T`, nên hợp lệ. Không cần raw type hay ép kiểu. Mẫu này chỉ đảm bảo **an toàn kiểu**; `set` vẫn có thể ném `UnsupportedOperationException` nếu danh sách được truyền vào không cho phép sửa.

## 6. Chọn kiểu cho tham số phương thức/API

### Chỉ cần quan sát hoặc xử lý chung: dùng `List<?>`

```java
static void printElements(List<?> elements) {
    for (Object element : elements) {
        System.out.println(element);
    }
}
```

`printElements` chấp nhận `List<String>`, `List<Integer>`, `List<Object>`... vì không cần biết hay cung cấp phần tử kiểu `E`. Đây là thiết kế phù hợp khi API không có nhu cầu liên hệ hoặc ghi một kiểu phần tử cụ thể.

### Thực sự cần đưa mọi loại đối tượng vào cùng một danh sách: dùng `List<Object>`

```java
static void recordEvent(List<Object> events, Object event) {
    events.add(event);
}
```

API này có ý nghĩa khi bên gọi **chủ động sở hữu** một danh sách có kiểu phần tử `Object`, cho phép chứa dữ liệu hỗn hợp. Không thể truyền `List<String>` vào vì phương thức có quyền thêm bất kỳ `Object` nào. Nếu dữ liệu cần đồng nhất kiểu, dùng tham số kiểu riêng như `<T>` thay vì mặc định lựa chọn `Object`.

### Cần duy trì quan hệ giữa đầu vào và đầu ra: dùng type parameter

```java
static <T> T firstOrNull(List<T> items) {
    return items.isEmpty() ? null : items.get(0);
}
```

Khi gọi với `List<String>`, kết quả có kiểu `String`; với `List<Integer>`, kết quả có kiểu `Integer`. Đối với một phép chỉ cần in các phần tử, `List<?>` dễ đọc hơn; đối với phép phải **giữ quan hệ kiểu `T`**, phương thức generic là giải pháp rõ ràng hơn.

### Khi yêu cầu đọc/ghi linh hoạt có giới hạn

`List<? extends Number>` cho phép nhận các danh sách kiểu phần tử là `Number` hoặc kiểu con, thích hợp để **đọc giá trị như `Number`**; không thể thêm một `Integer` bất kỳ vào danh sách chưa biết kiểu con. `List<? super Integer>` cho phép nhận `List<Integer>`, `List<Number>` hoặc `List<Object>` và **thêm `Integer`**; giá trị đọc ra chỉ bảo đảm là `Object`. Đây là các wildcard có giới hạn, mở rộng bài toán chứ không làm thay đổi sự khác biệt nền tảng của ba khai báo đang xét. Quy tắc gợi nhớ PECS (*Producer Extends, Consumer Super*) giúp chọn wildcard khi cần quan hệ kiểu cụ thể.

## 7. Raw `List`: khi nào tồn tại và cách đi qua ranh giới an toàn

Raw type thường gặp khi làm việc với API cũ được viết trước Java 5 hoặc các thư viện chưa khai báo kiểu. Ví dụ sau **cố ý minh họa thao tác không an toàn**, không nên dùng làm mẫu cho API mới:

```java
List raw = new ArrayList();
raw.add("ok");
raw.add(42);

List<String> assumedStrings = raw; // Unchecked conversion: compiler không xác minh được
// String second = assumedStrings.get(1); // Có thể ném ClassCastException
```

Tình huống này có **hai** chỗ rủi ro: gọi `add` trên raw `List` không kiểm tra tham số kiểu, rồi chuyển raw `List` thành `List<String>` tạo ra cam kết kiểu mà compiler không thể xác minh. Ép kiểu thành `List<String>` cũng **không** xác nhận từng phần tử do *type erasure* (tham số generic không được giữ như một kiểm tra toàn bộ nội dung ở runtime).

Một hướng xử lý đúng khi nhận danh sách không đáng tin là **xem dữ liệu qua `List<?>`, kiểm tra từng phần tử, và sao chép sang danh sách được định kiểu**:

```java
import java.util.ArrayList;
import java.util.List;

public class LegacyListValidationDemo {
    static List<String> validatedStrings(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object value : input) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected String element");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> legacyData = List.of("one", "two");
        List<String> safe = validatedStrings(legacyData);
        System.out.println(safe);
    }
}
```

Biên dịch `javac LegacyListValidationDemo.java` và chạy `java LegacyListValidationDemo`; stdout:

```text
[one, two]
```

Hàm trên chủ động **không chấp nhận `null`** vì `null instanceof String` là `false`. Nếu yêu cầu nghiệp vụ cho phép phần tử null, hãy xử lý quy tắc đó riêng. `result` là danh sách mới được kiểm tra từng phần tử; việc về sau có ai đó thay đổi `input` cũng không đưa phần tử sai kiểu vào `result` qua alias danh sách.

Khi buộc phải xử lý raw type ở một ranh giới tương thích, hãy khoanh vùng thật nhỏ nơi dùng raw/unchecked, xem xét dữ liệu trước khi chuyển thành cấu trúc có kiểu, và chỉ dùng `@SuppressWarnings("unchecked")` nếu có lý do cụ thể chứng minh thao tác là an toàn. Annotation này **chỉ ẩn cảnh báo**, không thêm kiểm tra runtime.

## 8. Những nhầm lẫn phổ biến

1. **“`String` extends `Object` nên `List<String>` extends `List<Object>`.”** Sai: quan hệ kế thừa của phần tử không tự truyền sang `List<E>`; Generics bất biến.
2. **“`List<?>` cũng là `List<Object>`.”** Sai: `?` là tham số kiểu chưa biết, không phải tên gọi khác của `Object`. Cả hai cùng đọc được dưới kiểu `Object` nhưng khác quyền ghi và quy tắc gán.
3. **“Wildcard không cho sửa danh sách.”** Sai: `add(null)`, `clear()`, `remove(...)` và những thao tác không cần một giá trị thuộc kiểu ẩn có thể hợp lệ về mặt kiểu. Quyền sửa đổi thực tế do implementation quyết định.
4. **“Raw type và wildcard đều nhận mọi danh sách nên tương đương.”** Sai: cả hai có thể nhận `List<String>`, nhưng raw type cho phép lời gọi thêm/sửa không được kiểm tra, còn wildcard giữ rào chắn an toàn tại compile time.
5. **“Cảnh báo unchecked không sao vì code biên dịch được.”** Sai: cảnh báo biểu thị vị trí compiler không chứng minh được an toàn kiểu; lỗi có thể lộ ra tại một lần đọc khác bằng `ClassCastException`.
6. **“`(List<String>) raw` sẽ kiểm tra mọi phần tử là `String`.”** Sai: do type erasure, việc ép kiểu danh sách không tự duyệt các phần tử. Muốn chắc chắn, phải kiểm tra dữ liệu hoặc dựa vào hợp đồng đáng tin của nguồn.
7. **“Dùng `List<Object>` ở mọi tham số giúp API linh hoạt hơn.”** Sai: tham số ấy lại từ chối `List<String>` và `List<Integer>`. Nếu chỉ đọc chung, `List<?>` thường linh hoạt và an toàn hơn.

## 9. Bài tự kiểm tra

Giả sử:

```java
List<Integer> nums = new ArrayList<>(List.of(1, 2));
List<?> a = nums;
List raw = nums;
List<Object> b = new ArrayList<>(nums);
```

Hãy dự đoán:

- `a.get(0)` và `b.get(0)` có kiểu tĩnh gì?
- `a.add(3)` có biên dịch không? `b.add("x")` có biên dịch không?
- `raw.add("x")` có biên dịch không, và rủi ro là gì?
- `b.add("x")` có làm `nums` thay đổi không?

**Đáp án:** Cả hai lời gọi `get(0)` có kiểu tĩnh `Object`; `a.add(3)` không biên dịch do kiểu ẩn, còn `b.add("x")` hợp lệ. `raw.add("x")` biên dịch nhưng có thể bị cảnh báo `unchecked` và làm ô nhiễm `nums`, khiến người đọc qua `List<Integer>` gặp lỗi ép kiểu lúc chạy. Thay đổi `b` không làm thay đổi cấu trúc `nums` vì `new ArrayList<>(nums)` đã tạo một danh sách mới.

## 10. Quy tắc chọn nhanh

- Dùng **`List<Object>`** khi muốn **một danh sách thực sự được phép chứa nhiều kiểu đối tượng** và chấp nhận việc đọc qua `Object`.
- Dùng **`List<?>`** khi cần **nhận/xem một danh sách có kiểu phần tử bất kỳ**, nhưng không cần đưa một phần tử có kiểu cụ thể vào danh sách. Nếu cần giữ liên hệ kiểu giữa nhiều giá trị, cân nhắc phương thức `<T>` hoặc wildcard có giới hạn.
- Tránh tạo API mới với **raw `List`**. Chỉ giữ nó ở ranh giới tích hợp legacy thật sự cần thiết, xử lý cảnh báo có chủ đích và kiểm tra dữ liệu trước khi nâng lên một `List<T>` đáng tin.

Một cách thử khi phân vân là hỏi: **“Tôi có quyền thêm một giá trị `Object` bất kỳ vào danh sách này không?”** Nếu có, `List<Object>` thể hiện hợp đồng phù hợp. Nếu không biết danh sách chứa kiểu gì và chỉ cần thao tác chung, `List<?>` thể hiện sự thiếu thông tin một cách an toàn. Raw `List` xóa mất phần bảo vệ mà Generics vốn được thiết kế để cung cấp.