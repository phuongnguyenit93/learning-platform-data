# Quy tắc cấm khóa `null` và giá trị `null` trong `Map.copyOf` (Java 10+)

## Mục tiêu

`Map.copyOf` là phương thức factory được bổ sung từ **Java 10** và vẫn được sử dụng trong các phiên bản Java hiện đại. Phương thức nhận một `Map` hiện có, trả về `Map` **không cho sửa** chứa các ánh xạ hiện tại. Một quy tắc cần ghi nhớ là: **kết quả của `Map.copyOf` không được chứa khóa `null` hoặc giá trị `null`**.

Bài học giúp bạn:

- Đọc chữ ký generic và các điều kiện đầu vào của `Map.copyOf`.
- Hiểu vì sao nguồn `HashMap` có thể hợp lệ nhưng `Map.copyOf(source)` vẫn ném `NullPointerException`.
- Phân biệt `null` ở **nguồn**, **khóa** và **giá trị**, kể cả trường hợp phần tử lỗi nằm sâu trong Map.
- So sánh với `Map.of`, `Map.ofEntries`, `Map.entry` và các implementation có chính sách `null` khác nhau.
- Kiểm tra, báo lỗi hoặc chuẩn hóa dữ liệu trước khi sao chép mà không vô tình làm mất thông tin nghiệp vụ.
- Phân biệt snapshot không cho sửa với deep copy, và viết ví dụ Java 17+ chạy độc lập.

## 1. Chữ ký và hợp đồng của `Map.copyOf`

Chữ ký phương thức `java.util.Map.copyOf`:

~~~java
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map)
~~~

**Giải thích:**

- `static`: gọi bằng `Map.copyOf(source)`, không gọi trên instance `source.copyOf()`.
- `<K, V>`: tham số kiểu generic của **phương thức**, ứng với kiểu khóa và kiểu giá trị.
- `Map<K, V>`: kiểu trả về; đây là một Map không cho sửa.
- `Map<? extends K, ? extends V>`: chấp nhận nguồn Map có kiểu khóa/giá trị tương thích với `K`/`V`, kể cả kiểu con.
- `map`: đối số nguồn phải **khác `null`**. Mỗi entry của nguồn phải có **khóa khác `null`** và **giá trị khác `null`**.

Ví dụ hợp lệ:

~~~java
Map<String, Integer> scores = Map.of("An", 9, "Binh", 8);
Map<String, Integer> immutableScores = Map.copyOf(scores);
~~~

Kết quả chứa các cặp khóa/giá trị như nguồn và từ chối sửa cấu trúc. Nếu sau đó `scores` được thay bằng một Map có thể sửa, điều đó **không** làm Map kết quả thay đổi. `Map.copyOf` không hứa luôn tạo object mới; với nguồn đã là unmodifiable Map thích hợp, implementation có thể trả lại cùng instance.

## 2. Ba trường hợp `null` đều bị từ chối

Java Collections Framework có những loại Map cho phép `null`, nhưng **`Map.copyOf` không nhận `null` ở bất kỳ vị trí nào dưới đây**:

| Dữ liệu đầu vào | Ví dụ | Hành vi |
| --- | --- | --- |
| Chính nguồn Map là `null` | `Map.copyOf(null)` | Ném `NullPointerException` |
| Một khóa `null` | Nguồn chứa ánh xạ `null -> 10` | Ném `NullPointerException` |
| Một giá trị `null` | Nguồn chứa ánh xạ `"An" -> null` | Ném `NullPointerException` |
| Khóa và giá trị đều khác `null` | Nguồn chứa `"An" -> 10` | Hợp lệ, giả sử nguồn Map hoạt động đúng hợp đồng |

Quy tắc áp dụng **với mọi entry**, không chỉ entry đầu tiên hoặc entry cuối cùng. Java không tự xóa entry lỗi, không biến `null` thành chuỗi `"null"`, không tạo Map chỉ chứa một phần các ánh xạ rồi trả về thành công.

Ví dụ minh họa (giả sử đặt trong phương thức với import `java.util.HashMap` và `java.util.Map`):

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("An", 9);
source.put(null, 7);       // HashMap cho phép một khóa null

// Map.copyOf(source);    // Ném NullPointerException

source.remove(null);
source.put("Binh", null);   // HashMap cũng cho phép giá trị null

// Map.copyOf(source);    // Vẫn ném NullPointerException
~~~

Các dòng `put` trên **không phải** là lỗi của `HashMap`; lỗi xuất hiện khi gọi factory `Map.copyOf`, do hợp đồng nghiêm ngặt hơn của **Map kết quả**.

## 3. Tại sao `HashMap` nhận `null` nhưng `Map.copyOf` thì không?

`Map` là một interface. Các implementation và factory có thể đưa ra các giới hạn khác nhau, miễn phù hợp với hợp đồng của chúng.

- `HashMap` cho phép một khóa `null` và cho phép giá trị `null` cho nhiều khóa.
- `LinkedHashMap` kế thừa chính sách cho phép `null` của `HashMap`.
- Không phải mọi Map đều cho phép `null` (ví dụ `ConcurrentHashMap` cấm cả khóa và giá trị `null`).
- `Map.copyOf`, `Map.of` và `Map.ofEntries` tạo kết quả không cho sửa **và cấm `null`**.

Vì vậy **“nguồn là Map hợp lệ” không đồng nghĩa “nguồn thích hợp để gọi `Map.copyOf`”**. Khi viết một phương thức nhận `Map<K,V>` từ bên ngoài, chỉ nhìn chữ ký `Map<K,V>` không chứng minh được nguồn sẽ không chứa `null`.

Bên cạnh đó, khi một `HashMap` chứa khóa `"An"` với giá trị `null`, `get("An")` trả `null`; nếu **không có** khóa `"An"`, `get("An")` cũng trả `null`. Với những Map cho phép `null`, dùng `containsKey("An")` khi cần phân biệt **có entry mang giá trị null** với **không có entry**.

## 4. `Map.copyOf` khác `Map.of` và `Map.ofEntries` như thế nào?

Cả ba đều cấm `null` nhưng **nguồn truyền vào khác nhau**:

~~~java
var byValues = Map.of("An", 9, "Binh", 8);

var byEntries = Map.ofEntries(
        Map.entry("An", 9),
        Map.entry("Binh", 8)
);

var source = new HashMap<String, Integer>();
source.put("An", 9);
source.put("Binh", 8);
var byCopy = Map.copyOf(source);
~~~

- `Map.of(k, v, ...)`: truyền trực tiếp các cặp khóa/giá trị; có các overload cho tối đa mười cặp.
- `Map.ofEntries(entry...)`: truyền các `Map.Entry`, thuận tiện khi có nhiều cặp; `Map.entry(k,v)` cũng cấm `null`.
- `Map.copyOf(source)`: truyền **một Map đã có**; không cần liệt kê từng cặp.

Các ví dụ cố ý gây lỗi:

~~~java
// Map.of(null, 1);            // NullPointerException: khóa null
// Map.of("An", null);         // NullPointerException: giá trị null
// Map.entry("An", null);      // NullPointerException ngay khi tạo entry
// Map.copyOf(sourceWithNull); // NullPointerException khi copy từ nguồn chứa null
~~~

Nếu gọi `Map.ofEntries(Map.entry("An", null))`, lỗi đã xảy ra ở bước **`Map.entry`**, trước khi `Map.ofEntries` xử lý danh sách entry. Không nên suy đoán tất cả lỗi của một biểu thức lồng nhau đều phát sinh tại cùng một phương thức.

Một điểm khác: `Map.of`/`Map.ofEntries` ném `IllegalArgumentException` với **khóa trùng** trong các đối số được liệt kê. Trong khi đó, một `Map` hợp lệ dùng làm nguồn của `Map.copyOf` đã có **khóa duy nhất**, nên không có hai entry trùng khóa để factory phát hiện ở đầu vào.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào tệp **MapCopyOfNullDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapCopyOfNullDemo {
    private static void tryCopy(String label, Map<String, Integer> source) {
        try {
            Map.copyOf(source);
            System.out.println(label + ": accepted");
        } catch (NullPointerException error) {
            System.out.println(label + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        var source = new HashMap<String, Integer>();
        source.put("An", 9);
        source.put("Binh", 8);

        var snapshot = Map.copyOf(source);
        source.put("Chi", 7);

        System.out.println("snapshot size: " + snapshot.size());
        System.out.println("snapshot An: " + snapshot.get("An"));
        System.out.println("snapshot has Chi: " + snapshot.containsKey("Chi"));

        var nullKey = new HashMap<String, Integer>();
        nullKey.put(null, 1);
        tryCopy("null key", nullKey);

        var nullValue = new HashMap<String, Integer>();
        nullValue.put("An", null);
        tryCopy("null value", nullValue);

        tryCopy("null source", null);

        try {
            Map.of("An", null);
        } catch (NullPointerException error) {
            System.out.println("Map.of null value: NullPointerException");
        }

        try {
            Map.entry("An", null);
        } catch (NullPointerException error) {
            System.out.println("Map.entry null value: NullPointerException");
        }

        try {
            snapshot.put("Duong", 10);
        } catch (UnsupportedOperationException error) {
            System.out.println("snapshot put: UnsupportedOperationException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac MapCopyOfNullDemo.java
java MapCopyOfNullDemo
~~~

Kết quả chuẩn:

~~~text
snapshot size: 2
snapshot An: 9
snapshot has Chi: false
null key: NullPointerException
null value: NullPointerException
null source: NullPointerException
Map.of null value: NullPointerException
Map.entry null value: NullPointerException
snapshot put: UnsupportedOperationException
~~~

**Phân tích:**

1. `snapshot` được tạo từ hai ánh xạ hợp lệ, có kích thước 2; sau khi nguồn thêm `"Chi"`, bản sao vẫn không có khóa này.
2. Hai `HashMap` chứa lần lượt khóa hoặc giá trị `null` đều được `HashMap` chấp nhận, nhưng `Map.copyOf` ném `NullPointerException`.
3. Đưa toàn bộ nguồn `null` vào `Map.copyOf` cũng ném `NullPointerException`, kể cả khi không có entry nào để duyệt.
4. `Map.of` và `Map.entry` từ chối giá trị `null` ngay trong factory tương ứng.
5. Map kết quả từ `copyOf` không hỗ trợ `put`, nên thao tác sửa ném `UnsupportedOperationException`.

Ví dụ chỉ in `size`, `get` và `containsKey`; không in toàn bộ `Map` theo thứ tự duyệt, vì `Map.copyOf` **không cam kết thứ tự duyệt**. Nội dung thông báo của ngoại lệ có thể thay đổi giữa các JDK; chương trình chỉ in tên lớp lỗi để có kết quả ổn định.

## 6. Cách kiểm tra nguồn trước khi gọi `Map.copyOf`

Nếu dữ liệu từ dịch vụ hoặc người dùng có thể chứa `null`, cần quyết định chính sách xử lý **trước khi** tạo Map không cho sửa.

### 6.1. Chính sách nghiêm ngặt: phát hiện và báo lỗi

Đây là lựa chọn phù hợp khi khóa và giá trị `null` biểu hiện lỗi dữ liệu:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class StrictCopy {
    public static <K, V> Map<K, V> checkedCopy(Map<K, V> source) {
        Objects.requireNonNull(source, "source");
        var checked = new HashMap<K, V>();

        for (var entry : source.entrySet()) {
            K key = Objects.requireNonNull(entry.getKey(), "null key");
            V value = Objects.requireNonNull(entry.getValue(), "null value");
            checked.put(key, value);
        }

        return Map.copyOf(checked);
    }
}
~~~

Đây là một **lớp độc lập** (lưu thành `StrictCopy.java` nếu muốn biên dịch riêng), không phải đoạn bổ sung vào `MapCopyOfNullDemo`.

Cách này giúp đưa ra thông báo lỗi có ý nghĩa hơn. Tuy nhiên, `checked` là bản sao tạm thời để kiểm tra; trong ứng dụng nhiều luồng, nếu dữ liệu nguồn có thể bị sửa đồng thời thì cần bảo đảm quyền truy cập nhất quán trong suốt quá trình đọc/copy. Các collection thông thường như `HashMap` không tự cung cấp một snapshot nguyên tử khi bị thay đổi đồng thời.

### 6.2. Chính sách có chủ đích: loại bỏ dữ liệu không hợp lệ

Chỉ làm khi nghiệp vụ cho phép bỏ những entry thiếu dữ liệu. Đoạn sau nằm trong một phương thức, với import `java.util.HashMap` và `java.util.Map`:

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("An", 9);
source.put("Binh", null);

Map<String, Integer> cleaned = new HashMap<>();
for (var entry : source.entrySet()) {
    if (entry.getKey() != null && entry.getValue() != null) {
        cleaned.put(entry.getKey(), entry.getValue());
    }
}

Map<String, Integer> result = Map.copyOf(cleaned);
~~~

Sau khi lọc, `result` không có entry `"Binh"`. **Đó là thay đổi dữ liệu nghiệp vụ**, không phải hành vi tự động của `Map.copyOf`. Nếu `null` có nghĩa là “chưa được nhập” hoặc “chưa biết”, việc bỏ entry có thể làm mất thông tin; phải có quyết định rõ ràng.

### 6.3. Cần biểu diễn giá trị có thể vắng mặt

Nếu phân biệt “có khóa nhưng chưa có giá trị” với “không có khóa” là một phần hợp đồng, không nên dùng `Map<String, Integer>` với `null` rồi mong `copyOf` giữ nguyên.

Một lựa chọn là mô hình hóa sự vắng mặt bằng một kiểu giá trị **khác null**, chẳng hạn `Optional<Integer>`, nếu nó phù hợp với API của bạn:

~~~java
Map<String, java.util.Optional<Integer>> values = Map.of(
        "An", java.util.Optional.of(9),
        "Binh", java.util.Optional.empty()
);

var snapshot = Map.copyOf(values);
~~~

Ở đây Map không chứa giá trị `null`; đối tượng `Optional.empty()` là một giá trị **khác null** mang ý nghĩa “không có số”. Đừng coi `Optional` là thay thế bắt buộc trong mọi mô hình dữ liệu; một kiểu trạng thái hoặc đối tượng nghiệp vụ riêng đôi khi phù hợp hơn.

## 7. Kiểu generic `K`, `V` không làm `null` tự biến mất

Java generics bảo đảm **tính tương thích kiểu tĩnh**, nhưng với kiểu tham chiếu thông thường, một biến `String` hay `Integer` vẫn có thể nhận `null`.

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("An", null); // Hợp lệ về mặt generic và được HashMap chấp nhận
// Map.copyOf(source);   // Ném NullPointerException
~~~

Ký hiệu `Map<String, Integer>` không tự động có nghĩa khóa hoặc giá trị không thể `null`. Điều đó phải đến từ **hợp đồng API**, kiểm tra dữ liệu hoặc công cụ phân tích tĩnh bổ sung của dự án.

Tương tự, `var snapshot = Map.copyOf(source)` không biến `null` thành một giá trị kiểu an toàn hơn. `var` chỉ suy luận kiểu từ biểu thức khởi tạo; nó không thay đổi các quy tắc runtime của `Map.copyOf`.

## 8. Về snapshot và tính bất biến

`Map.copyOf` tạo kết quả không cho sửa và không phản ánh việc thêm/xóa hoặc gán lại ánh xạ từ nguồn sau khi tạo. Tuy nhiên, phương thức **không tạo deep copy** của các đối tượng làm khóa hoặc giá trị.

Ví dụ minh họa trong một phương thức:

~~~java
var item = new StringBuilder("old");
var source = new HashMap<String, StringBuilder>();
source.put("name", item);

var snapshot = Map.copyOf(source);
item.append("-new");

System.out.println(snapshot.get("name")); // old-new
~~~

Map vẫn chỉ có ánh xạ `"name"` tới cùng đối tượng `StringBuilder`; trạng thái của đối tượng đó thay đổi được. Với **khóa mutable** mà `equals` hoặc `hashCode` phụ thuộc vào các trường thay đổi được, việc sửa khóa có thể làm hỏng tính đúng đắn của tra cứu Map; nên ưu tiên khóa bất biến.

Ngoài ra, `Map.copyOf` có thể tái sử dụng cùng instance khi nguồn đã là một unmodifiable Map thích hợp. **Không dùng `==` để kiểm tra việc sao chép**, cũng không đồng bộ hóa (*synchronize*) dựa trên danh tính các object factory này trả về. Hãy dựa vào hợp đồng về nội dung và tính không cho sửa.

## 9. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
| --- | --- | --- |
| “`HashMap` cho `null`, nên `Map.copyOf(hashMap)` cũng cho.” | Factory cấm `null` ở cả key và value. | Kiểm tra nguồn và quyết định chính sách trước khi copy. |
| “`null` value sẽ tự bị bỏ qua.” | `Map.copyOf` ném `NullPointerException`. | Chỉ lọc khi nghiệp vụ cho phép; đừng âm thầm làm mất entry. |
| “`Map.copyOf(null)` tạo Map rỗng.” | Ném `NullPointerException`. | Nếu muốn Map rỗng, gọi `Map.of()` với kiểu đích phù hợp. |
| “Đã khai báo `Map<String,Integer>` thì không thể có `null`.” | Generic không bảo đảm non-null. | Kiểm tra dữ liệu hoặc dùng hợp đồng/phân tích non-null phù hợp. |
| “Factory sẽ trả về Map có một phần dữ liệu trước khi gặp `null`.” | Lời gọi thất bại bằng ngoại lệ, không trả về kết quả thành công. | Xử lý lỗi và bảo toàn tính nhất quán của dữ liệu. |
| “`Map.copyOf` giữ nguyên thứ tự `LinkedHashMap`.” | Thứ tự duyệt kết quả không được cam kết. | Sắp xếp rõ ràng khi cần. |
| “`Map.copyOf` clone cả các object bên trong.” | Chỉ có snapshot ánh xạ; các object tham chiếu có thể mutable. | Dùng key/value bất biến hoặc copy sâu theo nghiệp vụ. |
| “`Map.copyOf` luôn cấp phát instance mới.” | Có thể tái sử dụng unmodifiable Map phù hợp. | Không phụ thuộc object identity. |

**Một lưu ý về lỗi runtime:** nếu nguồn được tạo bởi lời gọi factory khác, ví dụ `Map.of("An", null)`, `NullPointerException` phát sinh **ngay khi tạo nguồn**; không cần đến `Map.copyOf`. Hãy xác định chính xác bước thực sự thất bại trong stack trace, không chỉ nhìn tên biến kết quả.

## 10. Bài tập tự kiểm tra

Giả sử các đoạn mã được đặt trong một phương thức, đã import `java.util.HashMap`, `java.util.Map`:

~~~java
Map<String, Integer> a = new HashMap<>();
a.put("x", 1);
a.put(null, 2);

Map<String, Integer> b = new HashMap<>();
b.put("x", null);

Map<String, Integer> c = new HashMap<>();
c.put("x", 1);
c.put("y", 2);

// Tự dự đoán:
// 1. Map.copyOf(a) làm gì?
// 2. Map.copyOf(b) làm gì?
// 3. Map.copyOf(c) có hợp lệ không?
// 4. Sau khi copy c, nếu c.put("z", 3), bản sao có "z" không?
// 5. Map.copyOf(null) trả về gì?
~~~

**Đáp án:**

1. `Map.copyOf(a)` ném `NullPointerException` vì `a` chứa **khóa `null`**.
2. `Map.copyOf(b)` ném `NullPointerException` vì `b` chứa **giá trị `null`**.
3. `Map.copyOf(c)` hợp lệ: khóa và giá trị đều khác `null`.
4. Không. Bản sao không phản ánh việc thêm ánh xạ vào Map nguồn sau khi tạo.
5. Ném `NullPointerException`, không phải tạo Map rỗng.

**Câu hỏi mở rộng:** Làm sao vẫn lưu được trạng thái “có khóa `"x"` nhưng chưa có giá trị”, đồng thời tạo Map không cho sửa bằng `Map.copyOf`? Một cách là mô hình hóa value bằng một object không phải `null` (ví dụ `Optional<Integer>` hoặc một kiểu trạng thái riêng), và thống nhất ý nghĩa của kiểu đó với người sử dụng API.

## 11. Ghi nhớ và tài liệu chính thức

- **`Map.copyOf` từ chối ba trường hợp**: nguồn là `null`, bất kỳ khóa nào là `null`, hoặc bất kỳ giá trị nào là `null`.
- `HashMap`/`LinkedHashMap` có thể chứa `null`, nhưng điều đó không làm đầu vào `Map.copyOf` hợp lệ.
- `Map.of`, `Map.ofEntries` và `Map.entry` cũng cấm `null`.
- Kết quả `Map.copyOf` không cho sửa, không phản ánh các thay đổi ánh xạ trong Map nguồn về sau, nhưng không tự deep copy object làm key/value.
- Xử lý dữ liệu thiếu là **quyết định nghiệp vụ**: báo lỗi, bỏ entry có chủ đích, hoặc biểu diễn trạng thái thiếu bằng một kiểu khác `null`. Factory không quyết định hộ.

Nguồn tham khảo chuẩn:

- [Java SE 17 API — `Map.copyOf` và hợp đồng unmodifiable Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))
- [Java SE 17 API — `HashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [Java SE 17 API — `Map.of`, `Map.ofEntries`, `Map.entry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

**Kết luận:** Trước khi gọi `Map.copyOf(source)`, không chỉ hỏi “source có phải Map không?”, mà còn cần bảo đảm **source, mọi key và mọi value đều khác `null`**. Đây là quy tắc API vẫn áp dụng trong Java hiện đại.
