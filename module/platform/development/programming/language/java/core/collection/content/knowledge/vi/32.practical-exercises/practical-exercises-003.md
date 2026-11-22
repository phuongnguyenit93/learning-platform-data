# Đếm tần suất và nhóm dữ liệu bằng Map

Bài toán thực tế thường không chỉ cần lưu một danh sách, mà còn phải trả lời: một giá trị xuất hiện **bao nhiêu lần**, những bản ghi nào thuộc **cùng nhóm**, hoặc mỗi mã khách hàng gắn với **bao nhiêu đơn hàng**. `Map<K,V>` là mô hình thích hợp vì nó ánh xạ **khóa K** sang **một giá trị V**. Giá trị ấy có thể là số đếm, một danh sách, tập hợp hoặc cấu trúc kết quả khác.

Điểm cần thiết kế trước khi viết mã là *khóa đại diện cho điều gì*, *cách xem hai khóa là cùng một*, *có cần giữ thứ tự hay không*, và *giá trị nhóm phải giữ cả phần tử trùng hay loại trùng*.

## 1. Từ dữ liệu thô đến bảng tần suất

Cho luồng nhãn công nghệ:

```text
java, spring, java, jvm, spring, java
```

Mong muốn:

| Khóa | Tần suất |
| --- | ---: |
| java | 3 |
| spring | 2 |
| jvm | 1 |

Nếu duyệt danh sách và mỗi lần lại đếm từ đầu, mã lặp và chi phí tăng nhanh. Với `Map<String,Integer>`, ta giữ một kết quả tích lũy cho mỗi khóa. Bất biến sau khi xử lý `n` phần tử: tổng các giá trị đếm phải bằng `n` nếu mỗi đầu vào đều được tính đúng một lần và số đếm không tràn.

Một vòng lặp dễ đọc:

```java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String technology : technologies) {
    int previous = counts.getOrDefault(technology, 0);
    counts.put(technology, previous + 1);
}
```

`getOrDefault` lấy giá trị đang lưu, hoặc giá trị mặc định khi không có ánh xạ tương ứng; `put` ghi lại kết quả mới. Nếu giá trị đang được ánh xạ là `null`, `getOrDefault` **có thể trả `null`**, vì khóa thực sự có ánh xạ: khi viết bộ đếm, hãy chọn mô hình không lưu các giá trị `null`, hoặc xử lý riêng.

Với `HashMap`, thứ tự các khóa khi duyệt không được đảm bảo. `LinkedHashMap` mặc định giữ thứ tự chèn, thích hợp khi muốn in các khóa theo thứ tự xuất hiện đầu tiên. `TreeMap` sắp khóa theo comparator/`Comparable`, hữu ích khi báo cáo yêu cầu thứ tự chữ cái hoặc thứ tự số.

## 2. Dùng merge để rút gọn phép cộng dồn

`Map.merge(key, value, remappingFunction)` biểu đạt trực tiếp ý định gộp một giá trị mới vào giá trị đã có:

```java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String name : technologies) {
    counts.merge(name, 1, Integer::sum);
}
```

Cơ chế:

- Nếu khóa chưa có ánh xạ, hoặc giá trị được ánh xạ là `null`, `merge` nhận giá trị ban đầu `1`.
- Nếu khóa đã có giá trị khác `null`, hàm kết hợp nhận **giá trị cũ** và **giá trị mới** (ở đây là `1`) rồi trả kết quả.
- Nếu hàm kết hợp trả `null`, ánh xạ được **xóa**, vì vậy không được dùng `null` như một số đếm hợp lệ.
- Hàm kết hợp nên rõ ràng, tránh tự sửa cùng Map hoặc tạo hiệu ứng phụ khó dự đoán.

`Integer::sum` cộng bằng số nguyên `int` nên **có thể tràn** nếu số lần tăng vượt phạm vi `int`. Với hệ thống có thể đếm rất lớn, dùng `Long` và `Long::sum`, hoặc kiểm tra tràn theo yêu cầu.

## 3. Chương trình đếm tần suất chạy hoàn chỉnh

Tạo `FrequencyDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FrequencyDemo {
    public static void main(String[] args) {
        List<String> technologies = List.of(
                "java", "spring", "java", "jvm", "spring", "java"
        );

        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String technology : technologies) {
            counts.merge(technology, 1, Integer::sum);
        }

        System.out.println(counts);
        System.out.println("java: " + counts.getOrDefault("java", 0));
        System.out.println("kotlin: " + counts.getOrDefault("kotlin", 0));
        System.out.println("số nhóm: " + counts.size());

        int total = counts.values().stream()
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("tổng lượt: " + total);
    }
}
```

Biên dịch và chạy với JDK 17+:

```text
javac -encoding UTF-8 --release 17 FrequencyDemo.java
java -Dfile.encoding=UTF-8 FrequencyDemo
```

Đầu ra:

```text
{java=3, spring=2, jvm=1}
java: 3
kotlin: 0
số nhóm: 3
tổng lượt: 6
```

`counts.size()` là **số khóa phân biệt**, không phải tổng lượt. Tổng số lần xuất hiện nằm ở tổng các giá trị. Nếu bạn dùng `Set` cho dữ liệu đầu vào, các lần xuất hiện trùng có thể đã bị loại từ trước khi đếm; hãy giữ một `List` hoặc luồng sự kiện đầy đủ khi nghiệp vụ quan tâm tần suất.

Trong `LinkedHashMap` trên, lần xuất hiện đầu tiên quyết định vị trí hiển thị của khóa. `merge` tăng số đếm mà không tạo khóa mới, nên thứ tự chèn của các khóa không đổi.

## 4. Nhóm nhiều phần tử theo một khóa

Đếm lưu **một số** cho mỗi khóa. Nhóm dữ liệu lưu **một collection** cho mỗi khóa, thường là `Map<K,List<V>>`.

Ví dụ đầu vào `["Lan", "Linh", "Minh", "Mai", "Lan"]` và khóa là chữ cái đầu. Cần kết quả:

```text
L -> [Lan, Linh, Lan]
M -> [Minh, Mai]
```

Mã cốt lõi:

```java
Map<Character, List<String>> groups = new LinkedHashMap<>();
for (String name : names) {
    char initial = name.charAt(0);
    groups.computeIfAbsent(initial, ignored -> new ArrayList<>())
          .add(name);
}
```

Giải thích từng bước:

1. `computeIfAbsent` tìm giá trị đang gắn với khóa.
2. Nếu chưa có ánh xạ hữu dụng, hàm `ignored -> new ArrayList<>()` tạo list để chứa nhóm đó và lưu lại trong Map.
3. Kết quả trả về là list ứng với khóa; `add(name)` đưa phần tử vào nhóm.
4. Lần gặp lại khóa `L` sẽ sử dụng chính danh sách đã tạo trước đó; `Lan` xuất hiện hai lần nên vẫn có hai mục.

Với `computeIfAbsent`, nếu hàm mapping trả `null` thì **không tạo ánh xạ mới**; đoạn code nối `.add` khi đó có thể phát sinh `NullPointerException`. Ở ví dụ này `new ArrayList<>()` bảo đảm giá trị khác `null`. Không sửa cấu trúc Map ngay trong mapping function; Javadoc của từng implementation có các ràng buộc riêng.

## 5. Chương trình nhóm dữ liệu chạy hoàn chỉnh

Tạo `GroupingDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GroupingDemo {
    public static void main(String[] args) {
        List<String> names = List.of(
                "Lan", "Linh", "Minh", "Mai", "Lan"
        );

        Map<Character, List<String>> groups = new LinkedHashMap<>();
        for (String name : names) {
            char first = name.charAt(0);
            groups.computeIfAbsent(first, key -> new ArrayList<>())
                  .add(name);
        }

        System.out.println(groups);
        System.out.println("nhóm L: " + groups.get('L'));
        System.out.println("số nhóm: " + groups.size());
        System.out.println("số phần tử nhóm L: " + groups.get('L').size());
    }
}
```

Chạy:

```text
javac -encoding UTF-8 --release 17 GroupingDemo.java
java -Dfile.encoding=UTF-8 GroupingDemo
```

Đầu ra:

```text
{L=[Lan, Linh, Lan], M=[Minh, Mai]}
nhóm L: [Lan, Linh, Lan]
số nhóm: 2
số phần tử nhóm L: 3
```

Ở đây mọi tên đều không rỗng, vì vậy `charAt(0)` hợp lệ. Nếu đầu vào đến từ người dùng, phải định nghĩa chính sách cho `null`, chuỗi rỗng, khoảng trắng, chữ cái Unicode không nằm trong một `char` đơn, và cách chuẩn hóa. Không coi “ký tự đầu” tương đương “chữ cái đầu” với mọi ngôn ngữ: Unicode có ký tự ngoài BMP, dấu kết hợp và khác biệt chữ hoa/thường.

## 6. Map<K,List<V>> so với Map<K,Set<V>>

Cùng khóa nhóm, giá trị collection quyết định chính sách trùng lặp:

| Mô hình | Thích hợp khi | Điều phải nhớ |
| --- | --- | --- |
| `Map<K,Integer>` | Chỉ cần số lần xuất hiện | Không giữ các bản ghi gốc |
| `Map<K,Long>` | Số đếm có thể lớn | Vẫn phải xét khả năng tràn `long` trong cực trị |
| `Map<K,List<V>>` | Giữ mọi bản ghi, kể cả bản ghi trùng | Một phần tử có thể xuất hiện nhiều lần |
| `Map<K,LinkedHashSet<V>>` | Loại trùng trong từng nhóm, giữ thứ tự chèn | Trùng dựa trên `equals`/`hashCode` của V |
| `TreeMap<K,List<V>>` | Nhóm được hiển thị theo thứ tự khóa | Khóa cần so sánh ổn định, comparator phù hợp |

Ví dụ, “đếm 5 lượt check-in” không tương đương “5 người duy nhất”; cùng một người có thể check-in nhiều lần. Nếu khóa nhóm là mã lớp và danh sách là học viên, việc dùng `Set` có thể đúng; nếu danh sách là lịch sử lần điểm danh, dùng `List` sẽ phản ánh đầy đủ sự kiện.

Giá trị `List` là đối tượng có thể sửa. Khi trả `groups.get(key)` cho mã bên ngoài, mã đó có thể thay đổi trạng thái Map gián tiếp bằng cách sửa list. Nếu API chỉ được phép đọc, cân nhắc trả `List.copyOf(list)` khi không chứa null, hoặc một bản sao độc lập theo hợp đồng phù hợp. `Collections.unmodifiableList(list)` là view không cho sửa qua view, nhưng vẫn phản ánh thay đổi từ list gốc.

## 7. Chọn khóa nhóm cho bài toán thực tế

Khóa tốt phải thể hiện chính xác tiêu chí phân nhóm:

- Thống kê theo phòng ban: khóa là **mã phòng ban ổn định**, không phải tên hiển thị dễ đổi.
- Thống kê theo ngày: khóa là `LocalDate` trong múi giờ nghiệp vụ đã xác định, không tự lấy `Instant.toString().substring(...)`.
- Nhóm đơn hàng theo khách và trạng thái: dùng khóa ghép bất biến, chẳng hạn `record GroupKey(String customerId, Status status) {}`.
- Nhóm không phân biệt hoa/thường: chuẩn hóa đầu vào **theo chính sách rõ ràng** trước khi đưa vào Map, ví dụ `toLowerCase(Locale.ROOT)` cho mã kỹ thuật trong ngữ cảnh phù hợp. Với tên người và văn bản đa ngôn ngữ, cần quy tắc locale và chuẩn hóa riêng.

Hai khóa mà `equals` xem bằng nhau phải có cùng `hashCode`; khóa không được thay đổi theo cách phá hợp đồng khi còn ở trong HashMap. Không dùng đối tượng khả biến có `equals`/`hashCode` phụ thuộc trường có thể thay đổi làm khóa nhóm.

## 8. Stream groupingBy và toMap: khi nào nên dùng?

Stream cho phép diễn đạt gom nhóm ở mức khai báo:

```java
Map<Character, List<String>> groups =
        names.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        name -> name.charAt(0)
                )
        );
```

Kết quả nhóm về mặt phần tử có cùng mục đích với vòng lặp; nhưng overload mặc định của `groupingBy` **không cam kết loại Map hoặc thứ tự duyệt**. Nếu thứ tự chèn là yêu cầu, dùng overload có nhà cung cấp map:

```java
Map<Character, List<String>> groups =
        names.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        name -> name.charAt(0),
                        LinkedHashMap::new,
                        java.util.stream.Collectors.toList()
                )
        );
```

Với `toMap`, nếu nhiều phần tử tạo cùng khóa mà không có hàm xử lý trùng, phép gom có thể ném `IllegalStateException`. Đếm và nhóm vốn **chủ động chấp nhận khóa trùng**, vì vậy `groupingBy` hoặc `merge` thường rõ ý nghĩa hơn.

`groupingByConcurrent` và `ConcurrentHashMap` phục vụ một số bài toán đa luồng, nhưng không tự bảo đảm thứ tự chèn và có những điều kiện về collector, tính an toàn của giá trị. Đừng chuyển `HashMap` sang nhiều luồng ghi trực tiếp chỉ vì vòng lặp đơn luồng đúng; nếu đồng thời, xem xét hợp đồng `ConcurrentMap.merge` và chiến lược đồng bộ.

## 9. Lỗi thường gặp và cách tự kiểm chứng

1. **Nhầm `size()` với tổng số bản ghi:** `size()` của Map chỉ đếm khóa. Tổng tần suất = tổng các count.
2. **Đếm thiếu do dùng `Set` đầu vào:** hãy giữ dữ liệu sự kiện thô nếu cần cả phần tử lặp.
3. **Dựa vào thứ tự `HashMap`:** dùng `LinkedHashMap` cho thứ tự xuất hiện hoặc `TreeMap` cho thứ tự theo khóa.
4. **Gộp nhầm người bằng tên:** tên không phải mã định danh duy nhất, và chuẩn hóa phải rõ ràng.
5. **Thêm vào nhóm null:** kiểm tra mapping function không trả `null` trước khi gọi phương thức trên collection kết quả.
6. **Cộng dồn bị tràn:** dùng kiểu số và kiểm tra phù hợp với số liệu thực tế.
7. **Sửa khóa sau khi thêm:** có thể làm tra cứu HashMap không đáng tin cậy.
8. **Chia sẻ list nội bộ ra ngoài:** người gọi có thể sửa các nhóm; tạo bản sao/view tùy hợp đồng.
9. **Bỏ qua dữ liệu rỗng:** xác định việc bỏ qua, phân vào nhóm `UNKNOWN`, hay báo lỗi trước khi chạy.

### Bài thực hành

Với đầu vào `["A", "B", "A", "C", "B", "A"]`, dự đoán `counts` khi dùng `LinkedHashMap` với `merge`. Đáp án: `{A=3, B=2, C=1}`, tổng là 6 lượt và 3 khóa.

Sau đó, mở rộng bài tập thành nhóm theo chữ cái đầu của danh sách tên, giữ cả phần tử trùng. Thử thay giá trị `ArrayList` bằng `LinkedHashSet` và giải thích sự khác nhau giữa “số lượt” và “số đối tượng duy nhất”.

### Tự giải thích lại

Nếu bạn có thể trả lời bằng lời của mình ba câu sau, phần cốt lõi đã rõ: **(1)** Vì sao một Map có 3 khóa có thể đại diện cho 6 lượt? **(2)** `merge` và `computeIfAbsent` khác nhau ở đâu? **(3)** Khi nào dùng `Map<K,List<V>>` thay vì `Map<K,Set<V>>`?

## Tài liệu tham khảo

- Javadoc `Map` (Java SE 21) — `getOrDefault`, `merge` và `computeIfAbsent`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html
- Javadoc `LinkedHashMap` (Java SE 21) — thứ tự chèn: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html
- Javadoc `Collectors` (Java SE 21) — `groupingBy`, `toMap` và các overload: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html
