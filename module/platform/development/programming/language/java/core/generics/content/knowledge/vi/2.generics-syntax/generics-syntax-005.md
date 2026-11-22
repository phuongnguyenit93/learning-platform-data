# Kiểu tham số hóa lồng nhau trong Java: `Map<K, List<V>>`

Khi một cấu trúc dữ liệu chứa **một cấu trúc dữ liệu khác**, Java cho phép ghép các kiểu generic để diễn đạt đầy đủ kiểu ở từng tầng. Ví dụ `Map<String, List<Integer>>` là ánh xạ từ một `String` sang một danh sách `Integer`: mỗi khóa có thể gắn với nhiều số, trong khi trình biên dịch vẫn kiểm tra kiểu khóa, kiểu danh sách và kiểu phần tử.

Bài học tập trung vào cách **đọc, khai báo, khởi tạo và thao tác với kiểu tham số hóa lồng nhau**, đặc biệt mẫu `Map<K, List<V>>`. Sau bài này, bạn có thể viết phương thức generic cho cấu trúc ấy, chọn cách cập nhật an toàn, duyệt dữ liệu, xử lý khóa vắng mặt, nhận biết tính bất biến về kiểu và tránh nhầm lẫn giữa sao chép map với sao chép các danh sách bên trong.

## 1. Đọc đúng `Map<K, List<V>>` từ ngoài vào trong

Trước hết, `Map<K, V>` định nghĩa ánh xạ từ **một khóa kiểu `K`** tới **một giá trị kiểu `V`**. Khi giá trị đó là một danh sách, thay đối số kiểu thứ hai bằng `List<V>`:

```java
Map<K, List<V>>
```

Hãy đọc theo ba bước:

1. **Tầng ngoài — `Map<..., ...>`:** đây là cấu trúc ánh xạ khóa sang giá trị, với mỗi khóa duy nhất trong map.
2. **Đối số thứ nhất — `K`:** kiểu của khóa; `put` và `computeIfAbsent` cần khóa tương ứng với kiểu này.
3. **Đối số thứ hai — `List<V>`:** giá trị gắn với mỗi khóa là một danh sách; mỗi phần tử của danh sách có kiểu `V`.

Ở đây **`K` và `V` chỉ là tên tham số kiểu**, được khai báo bởi lớp/phương thức chứa chúng. Cấu trúc `Map<K, List<V>>` không mặc nhiên khai báo được `K` hoặc `V` trong mọi ngữ cảnh.

Ví dụ cụ thể:

```java
Map<String, List<Integer>> scores;
```

- `K` đã được thay bằng `String`: mỗi khóa là tên hoặc mã dưới dạng chuỗi.
- `V` đã được thay bằng `Integer`: mỗi danh sách chứa các số nguyên kiểu tham chiếu.
- Kiểu **giá trị của map** là `List<Integer>`, không phải `Integer`.
- Vì vậy, `scores.get("An")` có kiểu trả về `List<Integer>`; sau đó `scores.get("An").get(0)` có kiểu `Integer` nếu khóa tồn tại và danh sách không rỗng.

Mô hình dữ liệu:

```text
Map<String, List<Integer>>
    "An"    -> [8, 9, 10]
    "Bình"  -> [7, 9]
    "Chi"   -> []
```

Một map có thể có khóa trỏ tới danh sách rỗng, không có khóa đó, hoặc (nếu cách xây dựng cho phép) ánh xạ khóa tới `null`. Ba trạng thái này không nên mặc định được coi là giống nhau.

### Các ví dụ lồng kiểu khác

| Kiểu | Ý nghĩa |
| --- | --- |
| `List<List<String>>` | Danh sách mà mỗi phần tử là một danh sách chuỗi, ví dụ các hàng dữ liệu |
| `Map<String, List<Order>>` | Mỗi mã khách hàng liên kết với nhiều đơn hàng |
| `Map<Integer, Set<String>>` | Mỗi mã số liên kết với tập chuỗi không trùng |
| `Map<String, Map<String, Integer>>` | Ánh xạ hai cấp, ví dụ vùng → mặt hàng → số lượng |
| `List<Map<String, Object>>` | Danh sách các bản ghi có tên trường dạng chuỗi và giá trị đa kiểu |
| `Map<String, Optional<Long>>` | Mỗi khóa liên kết với một giá trị có thể có hoặc không, được biểu diễn bằng `Optional` |

Các kiểu như `Order` trong bảng là kiểu nghiệp vụ minh họa. `Map<String, List<V>>`, `Map<String, Set<V>>` hay `List<List<T>>` đều là **cú pháp kết hợp các kiểu generic**, không tạo nên loại cú pháp Java hoàn toàn mới.

## 2. Cú pháp khai báo, đóng ngoặc và toán tử kim cương

### 2.1. Khởi tạo với đối số kiểu cụ thể

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

Map<String, List<Integer>> scores = new HashMap<>();
scores.put("An", new ArrayList<Integer>());
```

Đây là **đoạn minh họa nằm trong phạm vi có thể khai báo biến cục bộ**, không phải tệp Java độc lập. Trong `new HashMap<>()`, dấu `<>` là *diamond operator*: trình biên dịch suy luận các đối số kiểu của đối tượng được khởi tạo từ ngữ cảnh biến bên trái. Đối tượng vẫn được dùng theo hợp đồng `Map<String, List<Integer>>`.

Đối với Java 7 trở lên, hai dấu `>` liên tiếp trong `Map<K, List<V>>` được nhận diện đúng để đóng hai danh sách tham số kiểu. Không cần chèn khoảng trắng giữa chúng.

```java
Map<String, List<Integer>> a = new HashMap<>();
Map<String, Map<Integer, List<Long>>> b = new HashMap<>();
```

Ví dụ thứ hai có ba dấu `>` liên tiếp vì có ba tầng generic cần đóng. Khi đọc cú pháp nhiều tầng, hãy ghép từng dấu `>` với dấu `<` tương ứng từ trong ra ngoài.

### 2.2. `Map<K, List<V>>` phải nằm trong phạm vi khai báo `K`, `V`

**Trong lớp generic:**

```java
final class Groups<K, V> {
    private final Map<K, List<V>> data = new HashMap<>();
}
```

**Trong phương thức generic:**

```java
static <K, V> void add(
        Map<K, List<V>> groups,
        K key,
        V value) {
    groups.computeIfAbsent(key, unused -> new ArrayList<>()).add(value);
}
```

Phần `<K, V>` **đứng trước kiểu trả về `void`** là khai báo tham số kiểu của phương thức. Tham số kiểu `K` xuất hiện ở khóa, `V` xuất hiện ở danh sách giá trị và đối số `value`, nhờ đó trình biên dịch kiểm tra các lời gọi cùng một hợp đồng.

Nếu viết phương thức sử dụng `K`, `V` bên trong một lớp không khai báo `K`, `V` và cũng không khai báo `<K, V>` tại phương thức, mã sẽ không biên dịch.

### 2.3. Tự suy luận kiểu không đồng nghĩa với raw type

```java
Map<String, List<Integer>> typed = new HashMap<>();
Map raw = new HashMap(); // Raw type: mất thông tin kiểu của khóa và giá trị.
```

`new HashMap<>()` ở dòng đầu **vẫn an toàn kiểu** theo biến `typed`; dòng thứ hai sử dụng kiểu thô (*raw type*), vốn có thể gây cảnh báo và lỗi khi chạy. Không nhầm hai trường hợp chỉ vì cả hai cùng viết ngắn ở phía khởi tạo.

## 3. Chương trình hoàn chỉnh: thêm, đọc, nhóm dữ liệu và tạo bản chụp

Lưu mã sau vào tệp **`Main.java`**. Chương trình dùng `Map<String, List<Integer>>` để lưu nhiều điểm theo tên; đồng thời có phương thức generic dùng lại cho nhiều kiểu khóa và giá trị. Một `record` được nhóm theo khóa để cho thấy cùng thuật toán hỗ trợ kiểu dữ liệu khác.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public class Main {
    record Enrollment(String course, String student) {}

    static <K, V> void append(
            Map<K, List<V>> groups,
            K key,
            V value) {
        groups.computeIfAbsent(key, unused -> new ArrayList<>()).add(value);
    }

    static <K, V> List<V> readSnapshot(
            Map<K, List<V>> groups,
            K key) {
        List<V> values = groups.get(key);
        return values == null ? List.of() : List.copyOf(values);
    }

    static <K, V> Map<K, List<V>> snapshot(
            Map<K, List<V>> groups) {
        Map<K, List<V>> copied = new LinkedHashMap<>();
        for (Map.Entry<K, List<V>> entry : groups.entrySet()) {
            copied.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        return Collections.unmodifiableMap(copied);
    }

    static <K, V> Map<K, List<V>> groupBy(
            List<V> items,
            Function<? super V, ? extends K> keySelector) {
        Map<K, List<V>> result = new LinkedHashMap<>();
        for (V item : items) {
            K key = keySelector.apply(item);
            append(result, key, item);
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        append(scores, "An", 8);
        append(scores, "An", 9);
        append(scores, "Bình", 7);

        System.out.println("Scores: " + scores);
        System.out.println("First An: " + readSnapshot(scores, "An").get(0));
        System.out.println("Missing: " + readSnapshot(scores, "Chi"));

        Map<String, List<Integer>> frozen = snapshot(scores);
        scores.get("An").add(10);

        System.out.println("Live An: " + scores.get("An"));
        System.out.println("Snapshot An: " + frozen.get("An"));

        List<Enrollment> registrations = List.of(
                new Enrollment("Java", "An"),
                new Enrollment("SQL", "Bình"),
                new Enrollment("Java", "Chi"));

        Map<String, List<Enrollment>> byCourse =
                groupBy(registrations, Enrollment::course);

        List<String> javaStudents = byCourse.get("Java").stream()
                .map(Enrollment::student)
                .toList();

        System.out.println("Java students: " + javaStudents);
        // append(scores, "An", "wrong"); // Sai kiểu: V của scores là Integer.
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
Scores: {An=[8, 9], Bình=[7]}
First An: 8
Missing: []
Live An: [8, 9, 10]
Snapshot An: [8, 9]
Java students: [An, Chi]
```

Giải thích kết quả:

1. `append(scores, "An", 8)` suy luận `K = String` và `V = Integer` từ đối số `Map<String, List<Integer>>` và tham số truyền vào. Không thể thêm một `String` vào danh sách điểm qua lời gọi cùng kiểu này.
2. `computeIfAbsent` chỉ tạo `ArrayList<V>` khi khóa chưa có ánh xạ giá trị khác `null`. Nếu đã có danh sách, nó trả danh sách đang lưu để `add` tiếp phần tử.
3. `readSnapshot` trả danh sách rỗng khi không có danh sách cho khóa, tránh việc gọi phương thức trên `null`. Khi có dữ liệu, nó dùng `List.copyOf` tạo danh sách không sửa được từ bên ngoài.
4. `snapshot` sao chép từng danh sách trước khi tạo map không sửa được. Vì thế thêm điểm `10` vào `scores` không làm thay đổi danh sách của `frozen`.
5. `groupBy` nhận `Enrollment::course` làm hàm tạo khóa, nhưng giữ chính `Enrollment` làm kiểu phần tử của danh sách. Kết quả `Map<String, List<Enrollment>>` thể hiện chính xác cả hai tầng dữ liệu.

**Phạm vi giả định của các hàm minh họa:** `snapshot` và `readSnapshot` yêu cầu danh sách/phần tử sao chép không phải `null`, vì `List.copyOf` ném `NullPointerException` với phần tử `null`. `snapshot` không sao chép sâu bản thân từng đối tượng `V` nếu chúng có trạng thái có thể thay đổi. `readSnapshot` chủ ý gộp hai trường hợp khóa vắng mặt và giá trị ánh xạ `null` thành danh sách rỗng; một API cần phân biệt trạng thái phải kiểm tra thêm bằng `containsKey`.

## 4. Truy cập và duyệt từng tầng dữ liệu

Với biến:

```java
Map<String, List<Integer>> scores = new LinkedHashMap<>();
```

các biểu thức sau có ý nghĩa kiểu khác nhau:

| Biểu thức | Kiểu tại thời điểm biên dịch | Lưu ý |
| --- | --- | --- |
| `scores` | `Map<String, List<Integer>>` | Toàn bộ ánh xạ |
| `scores.keySet()` | `Set<String>` | Tập các khóa |
| `scores.values()` | `Collection<List<Integer>>` | Tập hợp các danh sách; **không phải** `List<Integer>` |
| `scores.get("An")` | `List<Integer>` | Có thể là `null` nếu khóa không tồn tại hoặc được ánh xạ tới `null` |
| `scores.get("An").get(0)` | `Integer` | Chỉ an toàn nếu danh sách tồn tại và có phần tử đầu |
| `scores.entrySet()` | `Set<Map.Entry<String, List<Integer>>>` | Duyệt đồng thời khóa và danh sách |
| `scores.getOrDefault("Chi", List.of())` | `List<Integer>` | Dùng default nếu khóa **không có ánh xạ**; không thay thế giá trị `null` đang gắn với khóa |

Có ba cách duyệt hay gặp:

**Duyệt từng cặp khóa và danh sách:**

```java
for (Map.Entry<String, List<Integer>> entry : scores.entrySet()) {
    String name = entry.getKey();
    List<Integer> grades = entry.getValue();

    for (Integer grade : grades) {
        System.out.println(name + ": " + grade);
    }
}
```

Đây là mã minh họa dùng biến `scores` đã được khai báo và giả định các danh sách không `null`. Mỗi vòng `for` tương ứng một tầng tham số hóa. Với `HashMap`, thứ tự dòng in **không được bảo đảm**; chọn `LinkedHashMap` nếu cần giữ thứ tự chèn.

**Duyệt toàn bộ giá trị lồng nhau:**

```java
for (List<Integer> grades : scores.values()) {
    for (Integer grade : grades) {
        // Xử lý từng điểm grade.
    }
}
```

**Gộp phần tử từ nhiều danh sách bằng Stream:**

```java
List<Integer> allScores = scores.values().stream()
        .flatMap(List::stream)
        .toList();
```

Với Java 17, `Stream.toList()` tạo danh sách không thể sửa bằng các thao tác thêm/xóa trực tiếp. Nó không yêu cầu sắp xếp lại phần tử; thứ tự kết quả phụ thuộc thứ tự gặp phần tử của nguồn và các stream được tạo. Khi các danh sách đầu vào hoặc thứ tự lặp của map chưa xác định, không nên khẳng định một thứ tự đầu ra cụ thể.

## 5. Thao tác thêm phần tử: hiểu rõ danh sách bên trong có mutable không

Có hai cách viết thường gặp.

### 5.1. Tự tạo danh sách nếu thiếu khóa

```java
List<Integer> scoresOfAn = scores.get("An");
if (scoresOfAn == null) {
    scoresOfAn = new ArrayList<>();
    scores.put("An", scoresOfAn);
}
scoresOfAn.add(10);
```

Cách này phù hợp với map có thể thay đổi và các giá trị danh sách cũng có thể thay đổi. Nó coi khóa chưa tồn tại và khóa đang ánh xạ tới `null` như nhau.

### 5.2. Sử dụng `computeIfAbsent`

```java
scores.computeIfAbsent("An", key -> new ArrayList<>()).add(10);
```

`computeIfAbsent` hoạt động theo ý tưởng: nếu chưa có giá trị khác `null` cho khóa, tính giá trị mới qua lambda và gắn vào map; rồi trả về giá trị đó để dùng tiếp. Đây là cách gọn và đúng cho mẫu **một khóa → nhiều phần tử** trong ngữ cảnh map/danh sách mutable phù hợp.

**Không nhầm với `put`:**

```java
scores.put("An", new ArrayList<>(List.of(10)));
```

`put` trên khóa đã tồn tại sẽ **thay cả danh sách trước đó**, không chỉ thêm `10` vào danh sách hiện tại. Nếu muốn tích lũy phần tử, dùng `computeIfAbsent(...).add(...)` hoặc thao tác tương đương.

### Hai lỗi mutability phổ biến

**Map không sửa được:**

```java
Map<String, List<Integer>> immutableMap =
        Map.of("An", List.of(8, 9));
// immutableMap.put("Bình", List.of(7)); // UnsupportedOperationException.
```

**Danh sách không sửa được dù map có thể sửa:**

```java
Map<String, List<Integer>> mixed = new HashMap<>();
mixed.put("An", List.of(8, 9));
// mixed.get("An").add(10); // UnsupportedOperationException.
```

Không có quy tắc rằng `Map<K,List<V>>` luôn mutable hoặc luôn immutable. Khả năng sửa của **map ngoài** và **danh sách trong** là hai thuộc tính độc lập, phụ thuộc đối tượng triển khai. Một map mutable vẫn có thể chứa danh sách immutable.

Nếu API yêu cầu bất biến, hãy xác định nó có cho phép thay cả danh sách, thêm phần tử bên trong, hay không thao tác nào; sau đó thiết kế rõ hợp đồng đọc/ghi thay vì chỉ dựa vào tên kiểu generic.

## 6. Khóa vắng mặt, danh sách rỗng, `null` và kiểu trả về

Đọc:

```java
List<Integer> grades = scores.get("An");
```

Cần phân biệt:

- **Khóa không tồn tại:** `Map.get` thường trả về `null`.
- **Khóa tồn tại, giá trị `null`:** một số triển khai map cho phép; `get` cũng trả `null`, nhưng `containsKey("An")` là `true`.
- **Khóa tồn tại, danh sách rỗng:** `get` trả danh sách có `isEmpty() == true`, khác `null`.
- **Khóa tồn tại, danh sách có phần tử:** có thể duyệt và truy cập theo chỉ số hợp lệ.

Nếu luôn muốn danh sách rỗng cho khóa không tồn tại:

```java
List<Integer> grades = scores.getOrDefault("An", List.of());
```

Chú ý `getOrDefault` **không** thay thế giá trị `null` được ánh xạ rõ ràng bởi khóa. Nếu cần coi `null` giống vắng mặt:

```java
List<Integer> grades = scores.get("An");
if (grades == null) {
    grades = List.of();
}
```

Nếu cần phân biệt **vắng mặt** với **danh sách rỗng**, giữ nguyên hợp đồng `get` và dùng `containsKey` khi cần. Lạm dụng `List.of()` làm mặc định có thể làm mất thông tin nghiệp vụ, chẳng hạn “khách hàng chưa được tải lịch sử” khác với “lịch sử đã tải và rỗng”.

`List.of()` phù hợp làm **giá trị đọc mặc định** nhưng không thể `.add(...)`; muốn cập nhật phải tạo `new ArrayList<>()` hoặc chọn cấu trúc mutable thích hợp.

## 7. Bất biến kiểu ở nhiều tầng: lỗi biên dịch cần hiểu

Generics trong Java mặc định **bất biến (invariant)**. Dù `Integer` là subtype của `Number`, các kiểu `List<Integer>` và `List<Number>` không có quan hệ subtype theo chiều đó. Mức lồng nhau cũng không làm quy tắc này biến mất:

```java
Map<String, List<Integer>> grades = new HashMap<>();

// Không biên dịch:
// Map<String, List<Number>> asNumbers = grades;

// Không biên dịch:
// Map<String, List<? extends Number>> flexible = grades;
```

Tại sao phép gán thứ hai vẫn sai? `List<Integer>` có thể sử dụng ở nơi yêu cầu `List<? extends Number>`, nhưng **`Map<String, List<Integer>>` không phải subtype của `Map<String, List<? extends Number>>`** vì đối số kiểu thứ hai của `Map` cũng bất biến. Nếu cho gán, chỗ nhận có thể thay danh sách trong map bằng một danh sách `Double`, phá vỡ hợp đồng ban đầu.

Để viết API **chỉ đọc** các giá trị số từ nhiều loại danh sách, có thể mở rộng bằng wildcard đúng tầng:

```java
static double sumAll(
        Map<String, ? extends List<? extends Number>> source) {
    double total = 0;
    for (List<? extends Number> numbers : source.values()) {
        for (Number number : numbers) {
            total += number.doubleValue();
        }
    }
    return total;
}
```

Đây là phương thức minh họa, không phải chương trình độc lập. Kiểu `Map<String, ? extends List<? extends Number>>` cho phép nhận một map có giá trị là các danh sách với phần tử số phù hợp, bao gồm `Map<String, List<Integer>>`. Tuy vậy, qua tham chiếu `source` ta không thể thay tùy ý danh sách trong map bằng một `List<Number>` hay thêm một `Number` tùy ý vào danh sách nhận được. Cơ chế wildcard rộng hơn cho việc đọc nhưng **giới hạn một số thao tác ghi** để giữ an toàn kiểu.

Điểm cần nhớ: wildcard đặt ở **tầng nào** sẽ quyết định sự linh hoạt ở tầng đó. Ba chữ ký dưới đây khác nhau:

```java
Map<String, List<Number>>
Map<String, List<? extends Number>>
Map<String, ? extends List<? extends Number>>
```

Một API nhận chính xác kiểu thứ nhất là hợp đồng khác với API nhận kiểu thứ hai và kiểu thứ ba. Hãy bắt đầu từ nhu cầu sử dụng: cần đọc giá trị số, cần thêm loại số bất kỳ, hay cần thay cả danh sách?

### Lỗi thường gặp: gán map sang `Map<Object, ...>`

```java
Map<String, List<Integer>> scores = new HashMap<>();
// Map<Object, List<Object>> other = scores; // Không biên dịch.
```

Việc `String` là subtype của `Object` và `Integer` cũng là subtype của `Object` **không** làm các kiểu map liên quan trở thành subtype theo cách trên. Khi thực sự muốn chứa nhiều loại khóa và nhiều loại phần tử, cần thiết kế kiểu dữ liệu từ đầu, ví dụ `Map<Object, List<Object>>`, chấp nhận giảm độ chính xác của kiểu và kiểm tra dữ liệu ở ranh giới phù hợp.

## 8. Bài toán sao chép: map ngoài và danh sách trong

Một cấu trúc lồng nhau có thể chia sẻ tham chiếu giữa nhiều nơi:

```java
Map<String, List<Integer>> original = new HashMap<>();
original.put("An", new ArrayList<>(List.of(8, 9)));

Map<String, List<Integer>> shallow = new HashMap<>(original);
shallow.get("An").add(10);
```

`shallow` là **map mới**, nhưng `original.get("An")` và `shallow.get("An")` ban đầu trỏ tới **cùng một đối tượng danh sách**. Vì vậy, thêm `10` qua `shallow` cũng làm thay đổi danh sách nhìn từ `original`. Sao chép map **không tự động sao chép** các giá trị tham chiếu bên trong.

Tương tự, `Collections.unmodifiableMap(original)` chỉ tạo lớp xem không sửa được đối với map: bản thân các danh sách tham chiếu bên trong vẫn có thể mutable. `Map.copyOf(original)` tạo map không sửa được nhưng cũng không sao chép sâu từng danh sách; đồng thời không chấp nhận khóa/giá trị `null`.

Nếu muốn **bản chụp không sửa được ở hai tầng**, có thể sao chép danh sách trước:

```java
Map<String, List<Integer>> copied = new LinkedHashMap<>();
for (Map.Entry<String, List<Integer>> entry : original.entrySet()) {
    copied.put(entry.getKey(), List.copyOf(entry.getValue()));
}
Map<String, List<Integer>> frozen =
        Collections.unmodifiableMap(copied);
```

Cần hiểu chính xác giới hạn: `List.copyOf` chỉ sao chép cấu trúc danh sách và bảo đảm danh sách trả về không sửa được qua API đó; nó **không clone từng phần tử**. Nếu `V` là đối tượng có state mutable, muốn cách ly hoàn toàn state cần cơ chế tạo bản sao thích hợp cho chính kiểu `V`. Nếu dữ liệu đầu vào chứa `null`, `List.copyOf` ném `NullPointerException`.

Khi ngữ cảnh yêu cầu **cập nhật liên tục**, một cấu trúc mutable đơn giản như `LinkedHashMap<K, ArrayList<V>>` ở bên trong và chỉ phơi ra `Map<K,List<V>>`/danh sách sao chép ở API đọc có thể là lựa chọn hợp lý, nhưng cần nhất quán về quyền sửa và đồng bộ trong hệ thống nhiều luồng.

## 9. Khi nào nên dùng `Map<K,List<V>>`, khi nào cần cấu trúc khác?

`Map<K,List<V>>` phù hợp khi:

- Một khóa có **nhiều giá trị** và **thứ tự** hoặc khả năng lặp lại phần tử là quan trọng.
- Bạn cần nhóm dữ liệu theo thuộc tính, ví dụ khóa môn học → danh sách người đăng ký.
- Bạn cần tra nhanh nhóm theo khóa rồi duyệt các phần tử trong nhóm.

Nhưng không phải mọi quan hệ một-nhiều đều nên dùng `List<V>`:

| Nhu cầu | Lựa chọn tham khảo | Vì sao |
| --- | --- | --- |
| Cho phép giá trị lặp và lưu thứ tự trong mỗi nhóm | `Map<K, List<V>>` | List biểu diễn thứ tự và giữ bản sao các giá trị lặp |
| Không muốn phần tử lặp trong từng nhóm | `Map<K, Set<V>>` | Set diễn đạt tính duy nhất trong mỗi nhóm |
| Chỉ cần một giá trị trên mỗi khóa | `Map<K, V>` | Không cần thêm một tầng `List` |
| Cần nhóm hai cấp khóa độc lập | `Map<K1, Map<K2, V>>` | Mỗi cấp map mang một vai trò khóa |
| Cần giữ thứ tự toàn cục giữa mọi bản ghi | `List<Record>` hoặc model phù hợp | Nhóm theo khóa có thể che đi thứ tự xen kẽ ban đầu |
| Có nhiều quy tắc nghiệp vụ quanh nhóm | Lớp/domain object chuyên biệt | Đặt validation và thao tác nhất quán vào API có tên |

`HashMap` không bảo đảm thứ tự duyệt, còn `LinkedHashMap` giữ thứ tự chèn của khóa. Kiểu `List<V>` mô tả danh sách ở tầng giá trị nhưng không nói map ngoài là loại nào. Nếu thứ tự, tính duy nhất hay quyền thay đổi có ý nghĩa nghiệp vụ, hãy nêu rõ trong API hoặc chọn cấu trúc phù hợp.

### Nhóm dữ liệu bằng Stream

Một cách tạo kiểu lồng là `Collectors.groupingBy`:

```java
Map<String, List<Enrollment>> byCourse =
        registrations.stream()
                .collect(java.util.stream.Collectors.groupingBy(
                        Enrollment::course));
```

`Enrollment` và `registrations` lấy từ chương trình hoàn chỉnh ở phần 3. Kết quả có dạng `Map<String, List<Enrollment>>`. Không nên giả định thứ tự khóa hoặc loại/mutability chính xác của map và list do collector mặc định trả về; nếu những thuộc tính này là yêu cầu của API, hãy chọn overload với `mapFactory`/collector phù hợp hoặc chủ động tạo cấu trúc được kiểm soát.

Nếu muốn **giữ thứ tự gặp khóa** khi nhóm trong stream tuần tự, có thể dùng map factory:

```java
Map<String, List<Enrollment>> ordered =
        registrations.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        Enrollment::course,
                        LinkedHashMap::new,
                        java.util.stream.Collectors.toList()));
```

Đây là đoạn dùng trong ngữ cảnh tệp `Main.java` ở trên, không phải chương trình độc lập. Không nhầm "LinkedHashMap giữ thứ tự chèn khóa" với "mọi collector bảo đảm tính mutable và thứ tự trong mọi chế độ chạy". Hành vi thứ tự cần đọc từ hợp đồng của collector và đặc điểm stream đầu vào.

## 10. Type erasure và kiểm tra dữ liệu runtime

Sự an toàn kiểu của `Map<String, List<Integer>>` được kiểm tra chủ yếu **lúc biên dịch**. Java dùng cơ chế *type erasure*: tại runtime, phần lớn đối số kiểu như `String`, `Integer` trong cách tham số hóa không còn được reify trong một đối tượng map thông thường.

Vì vậy cú pháp sau không hợp lệ:

```java
// if (value instanceof Map<String, List<Integer>>) { ... }
// Không biên dịch: không kiểm tra được toàn bộ kiểu tham số hóa này.
```

Bạn có thể kiểm tra cấu trúc thô:

```java
if (value instanceof Map<?, ?>) {
    // Chỉ biết value là một Map, chưa biết kiểu khóa và giá trị bên trong.
}
```

Đây là đoạn minh họa dùng biến `value` kiểu `Object` đã tồn tại trong phạm vi. Khi dữ liệu đến từ JSON, phản hồi API, reflection hoặc mã raw, hãy **xác thực từng tầng**: kiểu khóa, kiểu giá trị có phải danh sách, và kiểu từng phần tử trước khi xem dữ liệu là `Map<String,List<Integer>>`.

Không nên viết một phép ép kiểu `((Map<String, List<Integer>>) value)` rồi xem đó là kiểm tra runtime đầy đủ. Phép ép không kiểm chứng có thể chấp nhận ở biên dịch kèm cảnh báo, nhưng dữ liệu sai bên trong vẫn dẫn tới lỗi khi truy cập sau đó. Với dữ liệu ngoài chương trình, dùng thư viện chuyển đổi có mô tả đầy đủ kiểu lồng nhau hoặc kiểm tra thủ công theo schema.

Về kỹ thuật, `Class<?>` đơn lẻ chỉ biểu diễn được lớp runtime, chẳng hạn `Map.class` hoặc `List.class`, chứ không biểu diễn đầy đủ `Map<String,List<Integer>>`. Một số thư viện JSON có cơ chế **type reference** cho kiểu generic lồng; cách sử dụng cụ thể tùy API của thư viện, không phải tính năng tự có của cú pháp Java.

## 11. Những lỗi điển hình và cách sửa

**Lỗi 1 — quên tầng `List`:**

```java
Map<String, List<Integer>> scores = new HashMap<>();
// scores.put("An", 8); // Sai: giá trị map phải là List<Integer>.
scores.put("An", new ArrayList<>(List.of(8))); // Hợp lệ.
```

**Lỗi 2 — đọc map như thể trả một `Integer`:**

```java
// Integer first = scores.get("An"); // Sai: get trả List<Integer>.
List<Integer> an = scores.get("An");
```

Muốn lấy phần tử đầu, cần `an.get(0)`, sau khi đảm bảo `an != null` và `!an.isEmpty()`.

**Lỗi 3 — chia sẻ một danh sách cho nhiều khóa ngoài ý muốn:**

```java
List<Integer> shared = new ArrayList<>();
scores.put("An", shared);
scores.put("Bình", shared);
```

Khi thêm phần tử qua một khóa, khóa còn lại nhìn thấy cùng thay đổi. Nếu muốn các nhóm độc lập, hãy tạo `new ArrayList<>()` riêng cho mỗi nhóm.

**Lỗi 4 — giả định `Map.of`/`List.of` có thể thêm phần tử:**

```java
Map<String, List<Integer>> fixed = Map.of("An", List.of(8));
// fixed.get("An").add(9); // UnsupportedOperationException.
```

Dùng các triển khai mutable khi thao tác cập nhật là yêu cầu, hoặc xây bản kết quả mới theo kiểu bất biến.

**Lỗi 5 — hiểu sai wildcard ở tầng trong:** `Map<String,List<Integer>>` không thể gán thẳng cho `Map<String,List<? extends Number>>`. Nếu một phương thức chỉ đọc nhiều loại danh sách số, hãy đánh giá `Map<String, ? extends List<? extends Number>>` cùng các giới hạn thao tác ghi.

**Lỗi 6 — trả trực tiếp danh sách nội bộ cho bên gọi:** bên nhận có thể `add`, `clear` hoặc thay đổi thứ tự, làm hỏng trạng thái của map. Dùng `List.copyOf`/view thích hợp và mô tả rõ đó là bản chụp hay một view sống.

**Lỗi 7 — coi `getOrDefault` như thay thế cả giá trị `null`:** phương thức chỉ lấy default khi khóa không có ánh xạ; kiểm tra `null` riêng nếu hợp đồng cần gộp hai trạng thái.

**Lỗi 8 — ép kiểu raw/unchecked khi dữ liệu không rõ nguồn:** thông tin kiểu generic có thể bị phá vỡ lúc chạy. Hãy kiểm tra cấu trúc ở biên dữ liệu, hạn chế raw type và xử lý cảnh báo `unchecked` có chủ đích.

## 12. Tự luyện tập

**Bài 1.** Cho:

```java
Map<String, List<Long>> ids = new HashMap<>();
```

Kiểu của `ids.get("A")` và `ids.values()` là gì?

**Đáp án:** `ids.get("A")` có kiểu `List<Long>`; `ids.values()` có kiểu `Collection<List<Long>>`. Không được kết luận rằng hai biểu thức tương đương với `Long` hoặc `Collection<Long>`.

**Bài 2.** Khi gọi:

```java
append(scores, "An", 9);
```

ở chương trình hoàn chỉnh, hai tham số kiểu được suy luận ra sao?

**Đáp án:** `K = String`, `V = Integer` vì `scores` là `Map<String,List<Integer>>`. Dòng `append(scores, "An", "9")` dùng chuỗi thay cho điểm số nguyên và bị từ chối khi biên dịch.

**Bài 3.** Vì sao `new HashMap<>(scores)` chưa đủ để tránh danh sách bên trong bị thay đổi từ một tham chiếu khác?

**Đáp án:** Hàm tạo ấy tạo một map mới nhưng sao chép các **tham chiếu giá trị**; những danh sách chứa trong cả hai map vẫn có thể là cùng đối tượng. Cần sao chép các danh sách khi muốn cách ly cấu trúc bên trong.

**Bài 4.** Một khóa chưa có điểm và một khóa có danh sách điểm rỗng có cùng ngữ nghĩa không?

**Đáp án:** Không nhất thiết. `get` trên khóa vắng mặt có thể trả `null`; khóa ánh xạ tới `List.of()` trả danh sách rỗng. Nghiệp vụ quyết định liệu có cần phân biệt và có nên sử dụng `containsKey` hay không.

**Bài 5.** Chọn chữ ký thích hợp cho một hàm **chỉ đọc** tất cả số trong các danh sách giá trị:

```java
Map<String, List<Number>>
Map<String, ? extends List<? extends Number>>
```

**Đáp án:** Chữ ký thứ hai linh hoạt hơn khi nhận `Map<String,List<Integer>>` hoặc các danh sách thuộc những loại con khác của `Number`. Đổi lại, API không thể tự do thay danh sách hay thêm các phần tử tùy ý qua tham chiếu wildcard.

## Tổng kết

Với `Map<K, List<V>>`, hãy đọc từ ngoài vào trong: map có khóa kiểu `K`, mỗi giá trị là danh sách phần tử kiểu `V`. Điểm mạnh của cú pháp lồng nhau là trình biên dịch có thể theo dõi **kiểu ở mọi tầng** và buộc `put`, `get`, `entrySet`, `computeIfAbsent` hay các phương thức generic tuân theo quan hệ đó. Để dùng đúng trong ứng dụng thực tế, hãy đồng thời quyết định **cấu trúc có mutable không, cần giữ thứ tự không, khóa vắng mặt xử lý ra sao và liệu bản sao map có đủ cách ly dữ liệu bên trong không**. Cuối cùng, nhớ rằng bất biến kiểu áp dụng ở từng tầng và type erasure không thay thế việc xác thực dữ liệu từ nguồn bên ngoài.