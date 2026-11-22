# Xây dựng chỉ mục nhiều giá trị với `Map<K, List<V>>`

## 1. Mục tiêu và bài toán

Sau bài này, bạn có thể tự xây dựng một **chỉ mục một khóa – nhiều giá trị** bằng Java Collections, tra cứu dữ liệu theo khóa, thêm/xóa phần tử, xử lý khóa không tồn tại và chọn giữa tự duy trì chỉ mục với gom nhóm bằng Stream.

Giả sử mỗi bản ghi đăng ký có **mã khóa học** và **sinh viên**. Một khóa học có nhiều sinh viên; một sinh viên cũng có thể học nhiều khóa. Ta muốn trả lời nhanh câu hỏi “Khóa Java có những sinh viên nào?” mà không quét lại toàn bộ danh sách đăng ký mỗi lần.

Dữ liệu ban đầu:

| Khóa học (K) | Sinh viên (V) |
| --- | --- |
| Java | S01 – An |
| Java | S02 – Binh |
| SQL | S03 – Chi |
| SQL | S01 – An |

Chỉ mục cần có dạng:

```text
Java -> [An, Binh]
SQL  -> [Chi, An]
```

Trong `Map<K, List<V>>`:

- `K` là khóa tra cứu, chẳng hạn `String` tên khóa học.
- `V` là **một** phần tử được lưu dưới khóa, chẳng hạn một `Student`.
- `List<V>` là nhóm nhiều phần tử ứng với một khóa; nó giữ **thứ tự chèn** và **cho phép phần tử trùng lặp**.
- `Map` giúp tìm nhóm theo khóa; `List` quản lý các phần tử bên trong nhóm.

Nếu dùng `Map<String, Student>` rồi gọi `put("Java", student)` nhiều lần, phần tử sau sẽ **ghi đè** phần tử trước. Vì vậy, với quan hệ một–nhiều, giá trị của map phải là một tập hợp, ở đây là `List<Student>`.

## 2. Quy tắc thiết kế trước khi viết mã

Một chỉ mục hữu dụng phải có hành vi rõ ràng:

1. **Thêm:** khóa chưa có thì tạo danh sách; khóa đã có thì thêm vào danh sách sẵn có.
2. **Tìm:** khóa chưa có trả về danh sách rỗng, tránh bắt người gọi xử lý `null`.
3. **Xóa:** xóa một giá trị bằng `equals`; nếu nhóm rỗng, xóa luôn khóa để không giữ mục không có dữ liệu.
4. **Trả kết quả:** đưa ra **bản chụp chỉ đọc** để mã bên ngoài không làm hỏng cấu trúc nội bộ.
5. **Thứ tự:** ví dụ này dùng `LinkedHashMap` để thứ tự các khóa khi duyệt theo thứ tự xuất hiện; mỗi danh sách dùng `ArrayList`.
6. **Giá trị null:** ví dụ chủ động từ chối khóa/giá trị `null` để API dễ kiểm tra và tương thích với `List.copyOf`.
7. **Trùng lặp:** `List` cho phép một giá trị xuất hiện nhiều lần; bài này giữ nguyên đặc tính đó. Nếu nghiệp vụ yêu cầu duy nhất, cần quy tắc riêng.

Để kiểm soát cập nhật, chương trình đóng gói `Map` trong một lớp `MultiValueIndex<K, V>`. Mọi thao tác qua `add`, `find`, `remove` và `counts`.

## 3. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`MultiValueIndexDemo.java`** với nội dung sau:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class MultiValueIndexDemo {
    record Student(String id, String name) {}

    record Enrollment(String course, Student student) {}

    static final class MultiValueIndex<K, V> {
        private final Map<K, List<V>> entries = new LinkedHashMap<>();

        public void add(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            entries.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
        }

        public List<V> find(K key) {
            Objects.requireNonNull(key, "key");
            List<V> values = entries.get(key);
            return values == null ? List.of() : List.copyOf(values);
        }

        public boolean remove(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            List<V> values = entries.get(key);
            if (values == null) {
                return false;
            }

            boolean removed = values.remove(value);
            if (values.isEmpty()) {
                entries.remove(key);
            }
            return removed;
        }

        public Map<K, Integer> counts() {
            Map<K, Integer> result = new LinkedHashMap<>();
            entries.forEach((key, values) -> result.put(key, values.size()));
            return Collections.unmodifiableMap(result);
        }
    }

    public static void main(String[] args) {
        Student an = new Student("S01", "An");
        Student binh = new Student("S02", "Binh");
        Student chi = new Student("S03", "Chi");

        List<Enrollment> registrations = List.of(
            new Enrollment("Java", an),
            new Enrollment("Java", binh),
            new Enrollment("SQL", chi),
            new Enrollment("SQL", an)
        );

        MultiValueIndex<String, Student> byCourse = new MultiValueIndex<>();
        for (Enrollment registration : registrations) {
            byCourse.add(registration.course(), registration.student());
        }

        System.out.println("Java: " + byCourse.find("Java"));
        System.out.println("SQL: " + byCourse.find("SQL"));
        System.out.println("Kotlin: " + byCourse.find("Kotlin"));
        System.out.println("So luong: " + byCourse.counts());

        List<Student> before = byCourse.find("Java");
        System.out.println("Xoa S01 khoi Java: " + byCourse.remove("Java", an));
        System.out.println("Java sau xoa: " + byCourse.find("Java"));
        System.out.println("Ban chup truoc do: " + before);

        byCourse.add("Java", chi);
        System.out.println("Java sau them: " + byCourse.find("Java"));
        System.out.println("So luong moi: " + byCourse.counts());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp (JDK 17 trở lên):

```bash
javac -encoding UTF-8 MultiValueIndexDemo.java
java MultiValueIndexDemo
```

Kết quả chuẩn:

```text
Java: [Student[id=S01, name=An], Student[id=S02, name=Binh]]
SQL: [Student[id=S03, name=Chi], Student[id=S01, name=An]]
Kotlin: []
So luong: {Java=2, SQL=2}
Xoa S01 khoi Java: true
Java sau xoa: [Student[id=S02, name=Binh]]
Ban chup truoc do: [Student[id=S01, name=An], Student[id=S02, name=Binh]]
Java sau them: [Student[id=S02, name=Binh], Student[id=S03, name=Chi]]
So luong moi: {Java=2, SQL=2}
```

`Student` và `Enrollment` là hai `record`: Java tự tạo constructor, phương thức truy cập (`id()`, `course()`, …), `equals`, `hashCode` và `toString` theo các thành phần record. Vì thế `values.remove(an)` có thể dùng so sánh giá trị, và kết quả in ra có định dạng `Student[id=..., name=...]`. Mã chạy độc lập, không cần thư viện bên ngoài.

## 4. Giải thích cơ chế cập nhật

### 4.1. `computeIfAbsent` tạo danh sách đúng lúc

Lệnh trọng tâm là:

```java
entries.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
```

- Nếu `key` chưa có ánh xạ, hàm tạo `ArrayList` mới, đưa danh sách vào map rồi trả về danh sách đó.
- Nếu `key` đã ánh xạ tới một danh sách khác `null`, phương thức trả lại **chính danh sách hiện có**.
- `add(value)` nối một phần tử vào cuối danh sách vừa nhận.
- Lambda `ignored -> ...` nhận khóa nhưng không cần sử dụng nó để tạo danh sách.

Cách viết thủ công tương đương về ý tưởng, trong trường hợp khóa/giá trị không `null` như ví dụ:

```java
List<V> values = entries.get(key);
if (values == null) {
    values = new ArrayList<>();
    entries.put(key, values);
}
values.add(value);
```

Không dùng `entries.put(key, new ArrayList<>(List.of(value)))` cho **mọi** lần thêm: lần thứ hai sẽ thay cả nhóm cũ, làm mất dữ liệu.

### 4.2. Tại sao kết quả `find` được sao chép?

`entries.get(key)` truy cập trực tiếp danh sách **có thể thay đổi** bên trong chỉ mục. Nếu trả tham chiếu đó ra ngoài, bên gọi có thể `clear()` hoặc `add()` mà không đi qua API của chỉ mục.

Trong ví dụ, `List.copyOf(values)` tạo danh sách **không cho sửa bằng các thao tác List** và lưu ảnh chụp thành viên tại thời điểm gọi. Vì thế biến `before` vẫn chứa An và Binh sau khi ta xóa An khỏi chỉ mục. `List.of()` là kết quả rỗng, cũng không chỉnh sửa được.

Lưu ý: đây là **sao chép nông**. Các đối tượng `V` bên trong không tự động được sao chép; nếu `V` là đối tượng mutable, trạng thái của chính đối tượng có thể vẫn đổi sau đó. Khi cần bất biến sâu, phải tự tạo bản sao phù hợp của từng phần tử.

Không nhầm hai lựa chọn:

- `List.copyOf(list)`: danh sách kết quả tách biệt về cấu trúc khỏi danh sách gốc.
- `Collections.unmodifiableList(list)`: chỉ là lớp bọc chỉ đọc; nếu danh sách gốc đổi, nội dung nhìn qua lớp bọc cũng đổi.

### 4.3. Xóa một lần xuất hiện và dọn khóa rỗng

`values.remove(value)` trả về `true` nếu tìm và xóa được **phần tử đầu tiên thỏa `equals`**; nếu không có, trả `false`. Hai bản ghi giống nhau được thêm hai lần sẽ cần hai lượt xóa để loại hết.

Sau khi xóa, `if (values.isEmpty()) entries.remove(key)` giữ bất biến: **không tồn tại khóa có nhóm rỗng**. Vì vậy `find` không cần phân biệt trường hợp khóa vắng mặt với nhóm còn tồn tại nhưng rỗng.

Ví dụ kiểm tra riêng (đoạn minh họa, dùng trong cùng lớp hoặc sau khi tạo một chỉ mục phù hợp):

```java
MultiValueIndex<String, String> tags = new MultiValueIndex<>();
tags.add("java", "collections");
tags.add("java", "collections");
tags.remove("java", "collections");
System.out.println(tags.find("java")); // [collections]
tags.remove("java", "collections");
System.out.println(tags.counts());      // {}
```

### 4.4. Tính số lượng theo từng khóa

`counts()` duyệt mỗi cặp `key -> list`, gán `list.size()` vào một map mới và trả về lớp bọc chỉ đọc. Đây là một **ảnh chụp số lượng**, không tự cập nhật sau khi chỉ mục đổi. Dùng `LinkedHashMap` cho kết quả đếm để giữ thứ tự khóa như chỉ mục gốc.

## 5. Cách khác: lập chỉ mục một lượt bằng Stream

Khi **đã có** toàn bộ danh sách `registrations` và chỉ cần nhóm một lần, có thể viết ngắn hơn bằng `Collectors.groupingBy`. Đoạn sau dùng các kiểu `Enrollment`, `Student` và biến `registrations` trong chương trình ở mục 3; cần thêm `import java.util.stream.Collectors;`:

```java
Map<String, List<Student>> grouped = registrations.stream()
    .collect(Collectors.groupingBy(
        Enrollment::course,
        LinkedHashMap::new,
        Collectors.mapping(
            Enrollment::student,
            Collectors.toCollection(ArrayList::new)
        )
    ));
```

- `Enrollment::course` chọn khóa cho mỗi bản ghi.
- `LinkedHashMap::new` giữ thứ tự xuất hiện của khóa.
- `Collectors.mapping` lấy `Student` từ `Enrollment`.
- `Collectors.toCollection(ArrayList::new)` tạo danh sách có thể cập nhật và giữ thứ tự gặp trong luồng tuần tự.

Với dữ liệu đang có, `grouped.get("Java")` chứa `[An, Binh]` (hiển thị bằng `Student.toString()` khi in ra). Luồng ví dụ là **sequential** nên thứ tự đầu vào được giữ như mô tả. `groupingBy` không nên dùng khi hàm phân nhóm có thể trả `null` mà chưa được xử lý; nó cũng không tự duy trì chỉ mục khi danh sách nguồn đổi.

Chọn **vòng lặp + `computeIfAbsent`** khi vừa đọc vừa thêm bản ghi, cập nhật tăng dần, xóa hoặc cần đóng gói quy tắc nghiệp vụ. Chọn **`groupingBy`** khi cần gom toàn bộ nguồn thành map trong một lần xử lý.

## 6. Độ phức tạp và lựa chọn collection

Gọi `n` là tổng số giá trị và `m` là số giá trị dưới một khóa:

| Thao tác | Chi phí điển hình | Nguyên nhân |
| --- | --- | --- |
| `add(key, value)` | O(1) trung bình, khấu hao | Tra map theo hash và thêm cuối `ArrayList` |
| Tìm danh sách nội bộ theo khóa | O(1) trung bình | `LinkedHashMap` dựa trên bảng băm |
| `find(key)` **trong ví dụ** | O(m) | Tra map rồi `List.copyOf` m phần tử |
| `remove(key, value)` | O(m) | Dò `equals`; `ArrayList` có thể dịch phần tử sau khi xóa |
| `counts()` | O(số khóa) | Duyệt từng nhóm và đọc `size()` |
| Bộ nhớ chỉ mục | O(n + số khóa) | Lưu tham chiếu giá trị và các danh sách/map |

Các ước lượng thao tác hash là **trung bình** khi `hashCode` phân bố phù hợp; không phải bảo đảm thời gian xấu nhất. `ArrayList` có lúc mở rộng mảng, vì vậy thêm cuối là O(1) **khấu hao**.

Chọn cấu trúc theo yêu cầu thực tế:

| Yêu cầu | Cấu trúc tham khảo |
| --- | --- |
| Cho phép trùng, cần thứ tự giá trị | `Map<K, List<V>>` |
| Không cho phép giá trị trùng theo `equals/hashCode` | `Map<K, Set<V>>`, ví dụ `LinkedHashSet<V>` |
| Cần duyệt khóa theo thứ tự chèn | `LinkedHashMap<K, List<V>>` |
| Cần sắp khóa theo comparator/thứ tự tự nhiên | `TreeMap<K, List<V>>` |
| Chỉ cần một giá trị cho một khóa | `Map<K, V>` |

**Không có một lựa chọn tốt nhất cho mọi trường hợp.** Nếu cần tra cứu hoặc xóa từng giá trị rất thường xuyên, `Set<V>` có thể thích hợp hơn. Nếu hai giá trị bằng nhau vẫn là hai lượt đăng ký khác nhau, `List<V>` là lựa chọn có ý nghĩa.

## 7. Các lỗi dễ gặp trong thực tế

**Ghi đè danh sách:** gọi `put` với danh sách mới ở mỗi bản ghi làm mất những giá trị trước đó. Hãy thêm vào nhóm sẵn có bằng `computeIfAbsent`.

**Sửa danh sách rỗng bất biến:** `map.getOrDefault(key, List.of()).add(value)` ném `UnsupportedOperationException` khi khóa chưa tồn tại vì `List.of()` là danh sách không thể sửa. `getOrDefault` cũng **không lưu** giá trị mặc định vào map. Dùng `computeIfAbsent` để khởi tạo nhóm có thể thay đổi.

**Rò rỉ dữ liệu nội bộ:** trả thẳng `entries.get(key)` khiến mã ngoài có thể sửa chỉ mục. Trả bản chụp `List.copyOf` nếu mục tiêu là API chỉ đọc có ảnh chụp.

**Dùng giá trị trùng mà không chủ đích:** `List` chấp nhận phần tử trùng. Nếu bài toán là đăng ký một sinh viên tối đa một lần cho mỗi khóa học, phải kiểm tra trùng bằng `contains` hoặc dùng `Set`. `contains` là O(m) và dựa vào `equals`.

**Mất đồng bộ khi nguồn đổi:** chỉ mục là dữ liệu dẫn xuất. Nếu một đăng ký chuyển từ Java sang SQL, phải **xóa phần tử khỏi nhóm Java rồi thêm vào nhóm SQL**, hoặc dựng lại chỉ mục từ nguồn thật. Chỉ sửa trường `course` trong đối tượng nguồn không tự chuyển phần tử giữa các danh sách.

**Khóa mutable:** `HashMap`/`LinkedHashMap` dựa trên `equals` và `hashCode` của khóa. Nếu thay đổi các trường tham gia hai phương thức đó sau khi đưa khóa vào map, việc tra cứu có thể sai. Ưu tiên khóa ổn định, chẳng hạn `String` hoặc record bất biến theo dữ liệu phù hợp.

**Nhầm an toàn luồng:** `LinkedHashMap` và `ArrayList` trong ví dụ **không thread-safe** khi nhiều luồng cùng thêm/xóa. Chỉ đổi map sang `ConcurrentHashMap` vẫn chưa làm `ArrayList` bên trong an toàn. Nếu thực sự có cập nhật đồng thời, cần thiết kế khóa đồng bộ hoặc cấu trúc concurrent tương ứng, xét cả thao tác tạo nhóm, sửa danh sách và xóa khóa rỗng.

**Nhầm chỉ mục với cơ sở dữ liệu:** map trong ví dụ nằm trong bộ nhớ; khi chương trình kết thúc, nó không tự được lưu xuống tệp hay cơ sở dữ liệu. Muốn bền vững phải lưu nguồn hoặc dữ liệu chỉ mục bằng cơ chế riêng.

## 8. Bài tập thực hành có tiêu chí kiểm tra

1. Tạo `MultiValueIndex<String, String>` lưu nhãn cho bài viết. Thêm `("p1", "java")`, `("p1", "map")`, `("p2", "java")`. Xác nhận `find("p1")` trả hai nhãn đúng thứ tự và `find("p3")` trả danh sách rỗng.
2. Thêm hai lần `("p1", "java")`. Quan sát `find("p1")` có hai giá trị `"java"`. Đổi yêu cầu thành **mỗi nhãn chỉ một lần**, rồi thử cách kiểm tra `contains` trước khi thêm hoặc thay `List` bằng `LinkedHashSet`.
3. Xóa lần lượt mọi giá trị thuộc `"p2"`. Xác nhận `counts()` không còn khóa `"p2"`. Gọi `remove` với khóa không có và kiểm tra kết quả `false`.
4. Ghi lại một kết quả `find("p1")` vào biến, thêm tiếp dữ liệu vào chỉ mục rồi in biến cũ. Giải thích vì sao ảnh chụp không đổi và vì sao người gọi không thể `add` trực tiếp vào danh sách đó.
5. Xây dựng chỉ mục ngược **`Map<String, List<String>>` từ nhãn sang mã bài viết**, ví dụ `"java" -> ["p1", "p2"]`. Xác định rõ một bài viết được gắn lại cùng nhãn nhiều lần thì có được lưu trùng hay không.

Tự kiểm tra: bạn cần giải thích được sự khác nhau giữa `Map<K,V>` và `Map<K,List<V>>`, cách `computeIfAbsent` tránh ghi đè, vì sao `find` ở đây tốn O(m), quy tắc dọn khóa rỗng và thời điểm nên dùng `groupingBy`. Khi tự triển khai chỉ mục cho bài toán khác, **hãy chốt trước** quy tắc trùng lặp, thứ tự, cập nhật và quyền sửa kết quả truy vấn.