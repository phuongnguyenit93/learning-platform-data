# Collection: Phân biệt sửa nguồn với tạo kết quả mới (Java 8+)

## 1. Đọc code và xác định: dữ liệu nào thật sự bị thay đổi?

Một chương trình Java có thể xử lý cùng một danh sách theo hai cách hoàn toàn khác nhau:

- **Sửa nguồn (mutation / in-place update):** thay đổi trực tiếp nội dung của Collection đang có, ví dụ thêm, xóa, thay thế hoặc sắp xếp phần tử.
- **Tạo kết quả mới (result materialization / copy):** đọc dữ liệu từ nguồn rồi tạo một đối tượng chứa kết quả riêng, chẳng hạn danh sách đã lọc hoặc danh sách đã chuyển đổi.

Điểm dễ nhầm là **cả hai cách đều có thể tạo ra một biến kết quả**. Có biến mới không có nghĩa dữ liệu mới độc lập, và có lời gọi trả về Collection không có nghĩa Collection đó là bản sao. Ví dụ, **subList** trả một **view** gắn với List gốc, trong khi **new ArrayList<>(source)** tạo cấu trúc danh sách khác.

Trong Java hiện đại, muốn biết một lời gọi có sửa nguồn hay không, phải kiểm tra **hợp đồng của API cụ thể** và cách viết lambda, không chỉ dựa vào tên phương thức.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết:

1. Phân biệt các phép thay đổi trực tiếp như **add**, **removeIf**, **replaceAll**, **sort**, **Map.put** với **Stream.filter/map/sorted** tạo kết quả khi thu thập.
2. Hiểu sự khác biệt giữa **bản sao độc lập về cấu trúc**, **unmodifiable snapshot**, **unmodifiable view** và **view có thể sửa nguồn**.
3. Hiểu vì sao **copy nông (shallow copy)** không bảo đảm độc lập với thay đổi bên trong đối tượng phần tử.
4. Chọn đúng API theo nhu cầu giữ dữ liệu gốc, sửa tại chỗ, bảo vệ kết quả hoặc tương thích Java 8.
5. Tránh side effect trong Stream và các lỗi khi sửa Collection đang được duyệt.

Tất cả kiến thức dưới đây còn có hiệu lực. Các API được bổ sung sau Java 8 sẽ được ghi rõ phiên bản.

## 2. Bảng định hướng: mutation, kết quả mới, và view

| Lời gọi | Sửa Collection nguồn? | Giá trị tạo ra / tính chất |
| --- | --- | --- |
| **list.add(x)** | Có, nếu List hỗ trợ | boolean hoặc void tùy overload |
| **list.remove(x)**, **list.removeIf(p)** | Có, nếu được hỗ trợ | boolean |
| **list.clear()** | Có, nếu được hỗ trợ | void |
| **list.set(i, x)** | Có, thay phần tử tại vị trí i | Trả phần tử cũ |
| **list.replaceAll(f)** | Có | void |
| **list.sort(comparator)** | Có | void |
| **Collections.sort(list)** | Có, trên List truyền vào | void |
| **list.stream().filter(p)** | Không tự sửa nguồn | Stream mới, chưa có List |
| **list.stream().map(f)** | Không tự sửa nguồn nếu mapper không có side effect | Stream mới, chưa có List |
| **list.stream().sorted()** | Không tự sắp xếp lại List nguồn | Stream mới, sau terminal có kết quả |
| **stream.collect(toCollection(ArrayList::new))** | Không sửa nguồn nếu pipeline thuần | ArrayList được tích lũy riêng |
| **stream.toList()** | Không tự sửa nguồn nếu pipeline thuần | List không hỗ trợ mutation, Java 16+ |
| **new ArrayList<>(list)** | Không | Bản sao cấu trúc có thể sửa, nông |
| **List.copyOf(list)** | Không | List không sửa được, không phản ánh thay đổi cấu trúc sau này; Java 10+ |
| **Collections.unmodifiableList(list)** | Không tự sửa, nhưng cũng **không copy** | View chỉ đọc, thay đổi từ List gốc vẫn nhìn thấy |
| **list.subList(from, to)** | Chưa sửa ngay; view có thể sửa List gốc | Danh sách con có liên kết với backing List |
| **map.keySet()**, **map.values()** | Chưa sửa ngay; nhiều thao tác trên view ảnh hưởng Map | View được hỗ trợ bởi Map gốc |

**Lưu ý:** Các phương thức sửa đổi trong interface Collection/List thường là **optional operations**. Một List không sửa được có thể ném **UnsupportedOperationException** khi gọi mutator. Không phải mọi biến khai báo kiểu **List<T>** đều có thể thêm/xóa phần tử.

Khái niệm **không sửa nguồn** trong Stream giả định mapper/predicate thực hiện đúng cách, không tự biến đổi List hay các đối tượng nguồn thông qua side effect.

## 3. Sửa trực tiếp List: thay đổi có thể quan sát ngay trên biến cũ

### 3.1. add, remove, clear và set

~~~java
List<String> source = new ArrayList<>(Arrays.asList("An", "Binh"));

source.add("Chi");       // source trở thành [An, Binh, Chi]
source.remove("Binh");   // source trở thành [An, Chi]
source.set(0, "Lan");    // source trở thành [Lan, Chi]
~~~

Các lời gọi trên sửa chính đối tượng ArrayList mà biến source đang tham chiếu. Nếu một biến khác cũng tham chiếu **cùng List**, nó nhìn thấy những thay đổi đó:

~~~java
List<String> source = new ArrayList<>(List.of("An", "Binh"));
List<String> alias = source; // Hai biến trỏ cùng một List.

alias.add("Chi");
System.out.println(source); // [An, Binh, Chi]
~~~

**Gán một tham chiếu mới vào biến không tạo bản sao.** Muốn hai cấu trúc danh sách độc lập, phải tạo một Collection kết quả riêng.

### 3.2. removeIf là mutation, khác filter

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("An", "Binh", "Chi", "Binh"));

source.removeIf("Binh"::equals);
System.out.println(source); // [An, Chi]
~~~

**removeIf** duyệt nguồn và xóa phần tử thỏa predicate nếu Collection hỗ trợ. Giá trị trả về là **boolean**: true khi có ít nhất một phần tử bị xóa, không phải danh sách đã lọc.

Trái lại:

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("An", "Binh", "Chi", "Binh"));

List<String> withoutBinh = source.stream()
        .filter(s -> !s.equals("Binh"))
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(source);      // [An, Binh, Chi, Binh]
System.out.println(withoutBinh); // [An, Chi]
~~~

Dòng **filter** mô tả giá trị giữ lại; phép thu thập vào ArrayList mới tạo kết quả. Nguồn không bị thay đổi. Đây là cặp thao tác nên so sánh đầu tiên khi chọn **in-place** hay **copy**.

### 3.3. replaceAll là mutation, khác map

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList(" an ", " binh "));

source.replaceAll(String::trim);
System.out.println(source); // [an, binh]
~~~

**List.replaceAll** thay thế từng phần tử của List bằng kết quả áp dụng hàm. Ngược lại:

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList(" an ", " binh "));

List<String> trimmed = source.stream()
        .map(String::trim)
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(source);  // [ an ,  binh ]
System.out.println(trimmed); // [an, binh]
~~~

**Stream.map** tạo một bước biến đổi logic trong pipeline. Không có Collection kết quả cho đến khi gọi terminal operation, ở đây là **collect**.

### 3.4. sort là mutation, khác sorted

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("Chi", "An", "Binh"));

source.sort(Comparator.naturalOrder());
System.out.println(source); // [An, Binh, Chi]
~~~

**List.sort** và **Collections.sort** thay đổi chính List được cung cấp nếu List cho phép thay thế phần tử. Trái lại:

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("Chi", "An", "Binh"));

List<String> sortedCopy = source.stream()
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(source);     // [Chi, An, Binh]
System.out.println(sortedCopy); // [An, Binh, Chi]
~~~

**Stream.sorted** là một intermediate operation. Với nguồn List có encounter order và một terminal operation bảo toàn thứ tự tương ứng, kết quả được sắp xếp mà List gốc không bị sắp lại.

## 4. Stream không tự sửa nguồn, nhưng lambda có thể làm điều đó

So sánh hai mapper:

~~~java
// Cách thuần, không sửa phần tử nguồn:
List<String> normalized = source.stream()
        .map(String::trim)
        .collect(Collectors.toList());

// Phản ví dụ: mapper có side effect lên object nguồn.
List<Employee> sameObjects = employees.stream()
        .map(e -> {
            e.setName(e.getName().trim()); // Thay đổi object đã có.
            return e;
        })
        .collect(Collectors.toList());
~~~

Đoạn thứ hai chỉ là **mã minh họa** giả định Employee có getName/setName; không phải chương trình chạy độc lập. Tuy Collectors tạo List kết quả, **đối tượng Employee cũ vẫn bị sửa** vì mapper gọi setter.

Các lambda trong Stream nên **stateless** và **non-interfering**: không can thiệp nguồn trong quá trình pipeline chạy và không phụ thuộc trạng thái mutable bị thay đổi. Đặc biệt, **không sửa Collection nguồn trong khi đang duyệt nó bằng Stream**.

Tình huống nguy hiểm:

~~~java
// Không làm thế này:
source.stream().filter(s -> {
    source.remove(s); // Sửa chính Collection đang được duyệt.
    return true;
}).count();
~~~

Đoạn trên có thể gây lỗi, kết quả không xác định theo mong muốn, hoặc bị tối ưu khiến các lambda không chạy theo cách người viết tưởng. **Không dựa vào side effect của Stream để biểu diễn nghiệp vụ cập nhật nguồn.**

Nếu yêu cầu là thay đổi nội dung nguồn, hãy chọn mutator thích hợp hoặc một cơ chế cập nhật có chủ đích. Nếu yêu cầu là biến đổi dữ liệu rồi lấy kết quả mới, hãy dùng pipeline thuần và collector thích hợp.

## 5. Chương trình chạy được: so sánh mutation, copy và view

Tạo tệp **CollectionMutationVsResultDemo.java**. Mã dùng Java 17+, bao gồm **List.copyOf** (Java 10+) và **Stream.toList** (Java 16+).

~~~java
import java.util.*;
import java.util.stream.*;

public class CollectionMutationVsResultDemo {
    static final class Person {
        String name;

        Person(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                Arrays.asList(" Lan ", "Binh", "An", "Binh"));

        List<String> filtered = source.stream()
                .filter(s -> s.startsWith("B"))
                .collect(Collectors.toCollection(ArrayList::new));

        System.out.println("source after filter: " + source);
        System.out.println("new filtered list: " + filtered);

        source.removeIf("Binh"::equals);
        source.replaceAll(String::trim);
        source.sort(Comparator.naturalOrder());

        System.out.println("source after mutations: " + source);

        List<String> independent = new ArrayList<>(source);
        independent.add("Minh");

        System.out.println("source after copy edit: " + source);
        System.out.println("editable copy: " + independent);

        List<String> unmodifiableView =
                Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("Hoa");

        System.out.println("view after source add: " + unmodifiableView);
        System.out.println("snapshot after source add: " + snapshot);

        try {
            unmodifiableView.add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view add: unsupported");
        }

        try {
            snapshot.add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add: unsupported");
        }

        source.add("Vy");
        List<String> sub = source.subList(1, 3);
        sub.set(0, "Linh");

        System.out.println("source after subList.set: " + source);

        List<String> upper = source.stream()
                .map(String::toUpperCase)
                .sorted()
                .toList();

        System.out.println("new upper list: " + upper);
        System.out.println("source after stream: " + source);

        try {
            upper.add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("stream.toList add: unsupported");
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("dev", 1);
        Set<String> keys = counts.keySet();
        counts.put("ops", 2);
        keys.remove("dev");

        System.out.println("map after keySet.remove: " + counts);

        Person p = new Person("An");
        List<Person> people = new ArrayList<>(List.of(p));
        List<Person> shallowCopy = List.copyOf(people);

        p.name = "An updated";
        people.add(new Person("Binh"));

        System.out.println("original people: " + people);
        System.out.println("shallow copy: " + shallowCopy);
        System.out.println("nullable stream list: "
                + Stream.of("A", null).toList());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CollectionMutationVsResultDemo.java
java CollectionMutationVsResultDemo
~~~

**Stdout chính xác:**

~~~text
source after filter: [ Lan , Binh, An, Binh]
new filtered list: [Binh, Binh]
source after mutations: [An, Lan]
source after copy edit: [An, Lan]
editable copy: [An, Lan, Minh]
view after source add: [An, Lan, Hoa]
snapshot after source add: [An, Lan]
view add: unsupported
snapshot add: unsupported
source after subList.set: [An, Linh, Hoa, Vy]
new upper list: [AN, HOA, LINH, VY]
source after stream: [An, Linh, Hoa, Vy]
stream.toList add: unsupported
map after keySet.remove: {ops=2}
original people: [An updated, Binh]
shallow copy: [An updated]
nullable stream list: [A, null]
~~~

### Giải thích các kết quả chính

1. **filter + collect(toCollection)** tạo một List mới chứa [Binh, Binh]. List nguồn vẫn còn bốn phần tử.
2. **removeIf**, **replaceAll**, **sort** lần lượt thay đổi List nguồn: xóa Binh, cắt khoảng trắng, sắp xếp để có [An, Lan].
3. **new ArrayList<>(source)** tạo cấu trúc List mới. Thêm Minh vào bản sao không làm nguồn tự có Minh.
4. **Collections.unmodifiableList(source)** trả một view không cho chỉnh sửa qua view, nhưng **source.add("Hoa")** khiến view nhìn thấy Hoa.
5. **List.copyOf(source)** tạo kết quả không sửa được và không phản ánh thay đổi cấu trúc của nguồn được sao chép. Snapshot vẫn [An, Lan].
6. **subList** là view gắn với List gốc: gọi **sub.set(0, "Linh")** làm source đổi từ Lan sang Linh.
7. **stream().map().sorted().toList()** tạo List kết quả không cho sửa trực tiếp; source vẫn [An, Linh, Hoa, Vy].
8. **keySet** là view của Map. Gọi **keys.remove("dev")** xóa khóa dev khỏi Map gốc.
9. **List.copyOf(people)** chỉ tạo bản sao nông: không nhận thêm Binh khi List nguồn được thêm phần tử, nhưng vẫn nhìn thấy Person "An updated" do hai List cùng giữ tham chiếu đến một Person.
10. **Stream.toList()** có thể chứa null, khác **List.copyOf** và **Collectors.toUnmodifiableList** vốn không chấp nhận null.

Mẫu chạy trên Java 17+ không cần phụ thuộc thư viện ngoài. Các phần dùng Stream và phương thức mutator cơ bản vẫn áp dụng cho Java 8; các API mới hơn được đánh dấu phiên bản cụ thể.

## 6. Bản sao cấu trúc: new ArrayList<>(source) có độc lập đến đâu?

Đoạn sau tạo hai List khác nhau về mặt cấu trúc:

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("An", "Binh"));

List<String> copy = new ArrayList<>(source);

copy.add("Chi");    // source vẫn [An, Binh].
source.remove("An"); // copy vẫn [An, Binh, Chi].
~~~

Đây là **shallow copy**:

- Thêm, xóa, thay thế **slot/phần tử trong danh sách** của một bên không tự sửa cấu trúc bên kia.
- Những phần tử là đối tượng tham chiếu **không được sao chép sâu**. Cả hai List có thể giữ cùng đối tượng mutable.
- Với **String** bất biến, ví dụ này dễ tạo cảm giác hai bản sao hoàn toàn độc lập; với object mutable, cần phân biệt rõ.

Ví dụ với object có thể sửa:

~~~java
// Giả sử Employee là một class có name mutable.
List<Employee> source = ...;
List<Employee> copy = new ArrayList<>(source);

copy.get(0).setName("Changed");
// Nếu hai List cùng tham chiếu một Employee, nguồn cũng quan sát
// được name đã đổi, dù cấu trúc List là hai bản khác nhau.
~~~

Đây là **mã minh họa** phụ thuộc class Employee do ứng dụng định nghĩa. Nếu cần **deep copy**, hãy tạo từng phần tử mới và sao chép những trường cần thiết theo hợp đồng nghiệp vụ. Không có một phép deep copy phổ quát được bảo đảm bởi **new ArrayList<>(source)** hoặc **List.copyOf**.

## 7. Unmodifiable không có nghĩa dữ liệu bất biến sâu

Ba khái niệm phải tách riêng:

- **Unmodifiable List:** không cho dùng các mutator để thay đổi trực tiếp cấu trúc List qua tham chiếu đó.
- **Unmodifiable view:** không cho sửa qua view, nhưng vẫn đọc dữ liệu trực tiếp từ backing Collection; thay đổi backing có thể hiện trên view.
- **Immutable value graph:** không chỉ cấu trúc ngoài mà cả giá trị bên trong đều không thể thay đổi theo cách quan sát được; cần thiết kế kiểu dữ liệu và sao chép phù hợp.

### Collections.unmodifiableList — view, không phải snapshot

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> readOnlyView =
        Collections.unmodifiableList(source);

source.add("B");

System.out.println(readOnlyView); // [A, B]
~~~

Không được gọi **readOnlyView.add(...)**, nhưng nguồn vẫn có thể bị sửa qua tham chiếu khác. Điều này thích hợp khi muốn cung cấp một cửa sổ chỉ đọc lên trạng thái đang được cập nhật có kiểm soát. **Không phù hợp** nếu yêu cầu là một snapshot ổn định, không phản ánh thay đổi về sau.

### List.copyOf — unmodifiable snapshot của cấu trúc

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(source);   // [A, B]
System.out.println(snapshot); // [A]
~~~

**List.copyOf** có từ Java 10, trả List không sửa được, không nhận null, và không phản ánh thay đổi cấu trúc sau đó của Collection được sao chép. **List.copyOf** có thể tái sử dụng một instance đã unmodifiable thay vì tạo một object mới; không được dựa vào danh tính tham chiếu hay giả định luôn có cấp phát mới.

Nếu phần tử là đối tượng mutable, thay đổi trạng thái của **chính phần tử** đó có thể hiện ở cả nguồn và snapshot. Muốn snapshot bất biến sâu, cần chọn các phần tử bất biến hoặc sao chép sâu theo miền dữ liệu.

### List.of — khởi tạo List không sửa được

~~~java
List<String> names = List.of("An", "Binh"); // Java 9+
~~~

**List.of** trả List không sửa được, không chấp nhận null; nó không phải API được giới thiệu trong Java 8. Các phần tử được cung cấp vẫn có thể là đối tượng mutable, nên không có bảo đảm bất biến sâu.

## 8. Stream tạo kết quả: cần phân biệt ba cách thu thập

### 8.1. Collectors.toCollection(ArrayList::new) — muốn List sửa được

~~~java
List<String> result = source.stream()
        .filter(s -> !s.isBlank())
        .collect(Collectors.toCollection(ArrayList::new));

result.add("New"); // Được phép do kết quả là ArrayList.
~~~

**String.isBlank()** có từ Java 11; nếu dự án phải chạy Java 8, thay predicate bằng điều kiện tương thích như **!s.trim().isEmpty()**, với sự khác biệt về Unicode whitespace cần cân nhắc theo đặc tả dữ liệu.

**Collectors.toCollection(ArrayList::new)** đã có từ Java 8, giúp chỉ rõ kiểu Collection muốn tạo. Nó không sửa Collection nguồn nếu mapper/predicate không có side effect.

### 8.2. Collectors.toList() — không tự giả định mutability

~~~java
List<String> result = source.stream()
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());
~~~

**Collectors.toList()** là collector từ Java 8. API không bảo đảm kiểu triển khai, mutability, thread-safety hay serializability của List trả về. Không nên viết code nghiệp vụ phụ thuộc vào việc hiện tại một JDK cụ thể trả ArrayList.

Nếu cần List chắc chắn có thể chỉnh sửa, chọn **toCollection(ArrayList::new)**.

### 8.3. Stream.toList() — unmodifiable, Java 16+

~~~java
List<String> result = source.stream()
        .filter(s -> !s.isEmpty())
        .toList(); // Java 16+
~~~

**Stream.toList()** là terminal operation trả List không hỗ trợ sửa đổi trực tiếp. Nó không hứa kiểu List cụ thể và có thể trả một instance có tính chất value-based; không dùng **==**, identity hash hay synchronization trên kết quả như cách xác định logic nghiệp vụ.

**Stream.toList() có thể chứa null**; trái lại, **Collectors.toUnmodifiableList()** (Java 10+) và **List.copyOf(...)** không chấp nhận phần tử null.

Để tương thích Java 8, dùng **collect(Collectors.toList())** khi không cần cam kết loại Collection, hoặc **toCollection(ArrayList::new)** khi cần một ArrayList sửa được. Đừng đổi hai cách đó sang Stream.toList() mà không kiểm tra nơi nhận có tiếp tục gọi add/remove hay không.

## 9. View có thể khiến thay đổi từ bên này xuất hiện ở bên kia

### 9.1. List.subList là view được hậu thuẫn bởi List nguồn

~~~java
List<String> names = new ArrayList<>(
        Arrays.asList("A", "B", "C", "D"));

List<String> middle = names.subList(1, 3); // [B, C]
middle.set(0, "X");

System.out.println(names); // [A, X, C, D]
~~~

**subList** không tự sao chép các phần tử. Thay đổi qua view có thể sửa List gốc. Nếu List gốc bị **sửa cấu trúc bên ngoài subList** khi view còn được sử dụng, hợp đồng List mô tả ngữ nghĩa của view có thể trở nên không xác định; với ArrayList thực tế có thể gặp ConcurrentModificationException. Không dựa vào lỗi đó như cơ chế đồng bộ.

Muốn cắt một đoạn thành **bản sao cấu trúc riêng**, viết:

~~~java
List<String> middleCopy =
        new ArrayList<>(names.subList(1, 3));
~~~

### 9.2. Arrays.asList là List kích thước cố định, gắn với mảng

~~~java
String[] data = {"A", "B"};
List<String> view = Arrays.asList(data);

view.set(0, "X");
System.out.println(Arrays.toString(data)); // [X, B]

// view.add("C") ném UnsupportedOperationException.
~~~

**Arrays.asList(array)** là List có kích thước cố định, được hậu thuẫn bởi mảng. **set** thay phần tử được, còn **add/remove** thay đổi kích thước thì không. Nó cũng không giống một **ArrayList** sao chép dữ liệu.

### 9.3. Map.keySet, values và entrySet là views

~~~java
Map<String, Integer> counts = new LinkedHashMap<>();
counts.put("dev", 1);
counts.put("ops", 2);

Set<String> keys = counts.keySet();
keys.remove("dev");

System.out.println(counts); // {ops=2}
~~~

Thay đổi qua view **keySet** có thể sửa chính Map. **values()** và **entrySet()** cũng là những view gắn với Map, với các thao tác được hỗ trợ theo loại Map và contract. Đừng gọi chúng là bản sao vì thấy kiểu trả về là Set hoặc Collection.

Muốn độc lập về cấu trúc, có thể tạo **new HashSet<>(map.keySet())** hoặc **new ArrayList<>(map.values())**. Những bản sao này vẫn nông nếu giá trị là mutable object.

## 10. Collection không nhất thiết cho phép mọi mutator

Java Collection Framework có các phương thức sửa đổi tùy chọn. Biến khai báo **List<String>** không cho biết chắc List đó sửa được hay không:

~~~java
List<String> editable = new ArrayList<>();
List<String> fixedSize = Arrays.asList("A", "B");
List<String> unmodifiable = List.of("A", "B"); // Java 9+
~~~

| Đối tượng | add/remove | set | Thay đổi qua nguồn khác |
| --- | --- | --- | --- |
| ArrayList thông thường | Có | Có | Alias cùng object thấy thay đổi |
| Arrays.asList(array) | Không (đổi kích thước) | Có | Mảng và List nhìn thấy thay đổi nhau |
| Collections.unmodifiableList(source) | Không qua view | Không qua view | Có, do source vẫn được phép sửa |
| List.of(...) | Không | Không | Không sửa cấu trúc List; phần tử mutable vẫn có thể đổi |
| List.copyOf(source) | Không | Không | Thay đổi cấu trúc source không hiện lên snapshot |
| Stream.toList() | Không | Không | Kết quả không sửa được; không tự biến thành view của source |

**Không dùng UnsupportedOperationException làm chiến lược luồng xử lý bình thường.** Chọn API tạo Collection phù hợp ngay tại ranh giới thành phần: cần sửa thì tạo bản sao có thể sửa; cần chia sẻ chỉ đọc thì xác định rõ view hay snapshot.

## 11. Mutating Map và tạo Map kết quả mới

Nguyên tắc tương tự áp dụng với Map:

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("dev", 2);
source.put("ops", 3);

source.replaceAll((key, count) -> count * 2);
// Source được sửa trực tiếp: dev=4, ops=6.
~~~

Nếu muốn xây Map kết quả khác:

~~~java
Map<String, Integer> result = source.entrySet().stream()
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                e -> e.getValue() * 2));
~~~

Đây là đoạn minh họa Java 8+ dùng **Collectors.toMap** để tạo Map kết quả. **toMap** không cam kết loại Map hoặc thứ tự khóa theo mặc định; muốn chọn loại Map, dùng overload nhận mapFactory thích hợp. Nếu keyMapper có thể tạo khóa trùng, cần định nghĩa merge function hoặc hiểu rằng overload không có merge sẽ báo lỗi.

**Map.copyOf(map)** (Java 10+) tạo Map không sửa được và không phản ánh các thay đổi cấu trúc về sau của nguồn, nhưng không tạo bản sao sâu của object làm value. **Collections.unmodifiableMap(map)** là view chỉ đọc gắn với Map gốc. Lựa chọn phụ thuộc ý nghĩa nghiệp vụ giống List.

## 12. Sửa Collection khi đang duyệt: lỗi dễ gặp

### 12.1. Vòng for-each và xóa trực tiếp

~~~java
List<String> names = new ArrayList<>(
        Arrays.asList("An", "Binh", "Chi"));

// KHÔNG nên xóa trực tiếp trong for-each:
// for (String s : names) {
//     if (s.equals("Binh")) names.remove(s);
// }
~~~

Với ArrayList, việc sửa cấu trúc Collection khi Iterator đang duyệt theo cách ngoài iterator có thể gây **ConcurrentModificationException**. Nhưng fail-fast là cơ chế phát hiện **best effort**, không phải công cụ đảm bảo an toàn đồng thời.

Cách phù hợp khi muốn sửa nguồn:

~~~java
names.removeIf("Binh"::equals); // [An, Chi]
~~~

Hoặc nếu cần logic phụ thuộc Iterator, dùng **Iterator.remove()** đúng hợp đồng trên Collection cho phép:

~~~java
Iterator<String> iterator = names.iterator();
while (iterator.hasNext()) {
    if (iterator.next().equals("Chi")) {
        iterator.remove();
    }
}
~~~

Cách phù hợp khi không muốn sửa nguồn:

~~~java
List<String> withoutBinh = names.stream()
        .filter(s -> !s.equals("Binh"))
        .collect(Collectors.toCollection(ArrayList::new));
~~~

### 12.2. Sửa nguồn trong parallelStream hoặc ghi vào List chia sẻ

~~~java
List<Integer> shared = new ArrayList<>();

// KHÔNG nên dùng kiểu này:
source.parallelStream().forEach(item -> {
    shared.add(item.length()); // Ghi vào ArrayList dùng chung: nguy cơ race.
});
~~~

Đoạn minh họa giả định source có phần tử String. **ArrayList không hỗ trợ các lần add đồng thời không được đồng bộ**. Không sửa Collection đang được Stream duyệt và không dùng biến mutable dùng chung trong lambdas của parallel stream.

Thay bằng collector:

~~~java
List<Integer> lengths = source.parallelStream()
        .map(String::length)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Collector kết hợp kết quả theo contract thay vì để các worker tự ghi vào cùng một ArrayList. Dù vậy, **thứ tự thực thi mapper** trên các thread có thể khác encounter order, nên tránh side effect phụ thuộc lịch chạy.

### 12.3. Sao chép trước khi thay đổi

Nếu một method có nhiệm vụ "tạo kết quả đã chuẩn hóa" mà không được chạm vào source:

~~~java
static List<String> sortedTrimmedCopy(
        Collection<String> source) {
    return source.stream()
            .map(String::trim)
            .sorted()
            .collect(Collectors.toCollection(ArrayList::new));
}
~~~

Đây là phương thức minh họa đầy đủ, cần import **Collection, List, ArrayList, Collectors**. Hàm chỉ đọc các String và trả ArrayList có thể sửa, không gọi mutation lên Collection đầu vào. Nếu nguồn chứa null, mapper phải được điều chỉnh theo quy tắc null của nghiệp vụ.

## 13. Khi nào nên chọn sửa nguồn?

**Sửa nguồn** có thể hợp lý khi:

- API của bạn **được phép** thay đổi Collection truyền vào, được ghi rõ bằng tên/hợp đồng method.
- Collection có thể sửa, không bị chia sẻ cho những phần khác cần giá trị cũ.
- Không có iterator/view đang phụ thuộc vào cấu trúc cũ theo cách không tương thích.
- Muốn tránh tạo container mới khi không cần giữ hai trạng thái.
- Có quy tắc rõ về đồng bộ và ownership nếu nhiều thread truy cập.

Ví dụ phương thức chủ động sửa List:

~~~java
static void normalizeInPlace(List<String> names) {
    names.replaceAll(String::trim);
    names.removeIf(String::isEmpty);
    names.sort(Comparator.naturalOrder());
}
~~~

Đây là phương thức minh họa, yêu cầu List có thể sửa và không chứa null; có thể dùng với ArrayList. Tên **InPlace** là tín hiệu rõ cho người gọi biết đầu vào sẽ bị thay đổi.

**Không mặc định sửa Collection của bên gọi** trong một phương thức có tên giống như truy vấn thuần. Nếu phải sửa, hãy thể hiện trong contract hoặc trả về kết quả mới để tránh side effect bất ngờ.

## 14. Khi nào nên tạo kết quả mới?

**Tạo kết quả mới** thường hợp lý khi:

- Muốn giữ dữ liệu đầu vào để so sánh, audit, hoặc dùng lại.
- Nhiều thành phần cùng đọc nguồn và không nên chịu tác động của thay đổi bất ngờ.
- Xây pipeline lọc, ánh xạ, sắp xếp hoặc nhóm dữ liệu theo yêu cầu.
- Cần làm rõ output có thể sửa hay không sửa.
- Muốn kiểm thử method bằng cách so sánh đầu vào trước/sau.

~~~java
static List<String> normalizedCopy(
        Collection<String> names) {
    return names.stream()
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .sorted()
            .collect(Collectors.toCollection(ArrayList::new));
}
~~~

Nếu không muốn người nhận sửa output và dự án dùng Java 16+, có thể dùng **stream().map(...).sorted().toList()**. Nếu nguồn chứa object mutable và yêu cầu bảo toàn trạng thái sâu, tạo List mới **chưa đủ**; cần thiết kế kiểu phần tử hoặc sao chép sâu.

**Chi phí:** tạo List/Map mới có thể dùng thêm bộ nhớ và tăng áp lực cấp phát, đặc biệt với dữ liệu lớn. Mutation có thể rẻ hơn, nhưng dễ mang side effect và khó bảo toàn phiên bản dữ liệu. Chọn theo contract và benchmark thực tế khi hiệu năng quan trọng.

## 15. Các lỗi về phiên bản Java và null

| API | Có từ | Ghi chú vẫn còn áp dụng |
| --- | --- | --- |
| Collection.removeIf | Java 8 | Sửa nguồn nếu được hỗ trợ |
| List.replaceAll, List.sort | Java 8 | Sửa List đầu vào |
| Stream.filter/map/sorted/collect | Java 8 | Tạo pipeline, terminal collector materialize |
| Collectors.toList / toCollection | Java 8 | toList không bảo đảm khả năng sửa; toCollection cho chọn kiểu |
| Collections.unmodifiableList | Có trước Java 8, vẫn hiện hành | Unmodifiable view, không copy |
| List.subList | Có trước Java 8, vẫn hiện hành | View gắn với backing List |
| List.of | Java 9 | List không sửa được, không nhận null |
| List.copyOf | Java 10 | Unmodifiable structural snapshot; không nhận null |
| Collectors.toUnmodifiableList | Java 10 | Unmodifiable, không nhận null |
| String.isBlank | Java 11 | Kiểm tra chuỗi trắng theo định nghĩa Unicode của API |
| Stream.toList | Java 16 | Unmodifiable List, cho phép null |
| Map.copyOf | Java 10 | Unmodifiable Map, snapshot cấu trúc, không nhận null |

**Không nhầm Java 8 là phiên bản cuối cùng của các API liên quan.** Một bài học trong module Java 8 có thể giải thích lựa chọn hiện hành từ Java 10/16, nhưng phải nói rõ yêu cầu phiên bản để code không âm thầm lỗi khi biên dịch trên JDK 8.

### Null cần xử lý theo hợp đồng

~~~java
List<String> withNull = new ArrayList<>(
        Arrays.asList("A", null));

List<String> editableCopy = new ArrayList<>(withNull);
// Có thể chứa null.

List<String> streamResult = withNull.stream().toList();
// Java 16+: cũng có thể chứa null.

// List.copyOf(withNull) ném NullPointerException.
// withNull.stream().collect(Collectors.toUnmodifiableList())
// cũng ném NullPointerException (Java 10+).
~~~

Ví dụ trên gồm những đoạn minh họa cho từng API; các dòng gây lỗi được để dưới dạng nhận xét. Các kết quả này không suy ra rằng một List không sửa được nói chung phải chấp nhận null. **Mỗi API có contract riêng**.

## 16. Quy trình xác định một lời gọi có sửa nguồn hay không

Khi đọc code Collection, hãy kiểm tra theo thứ tự:

1. **Xác định đối tượng sở hữu dữ liệu**: List/Set/Map đến từ đâu, ai còn giữ tham chiếu?
2. **Xem API có là mutator không**: add, remove, removeIf, clear, replaceAll, sort, put, compute... là các dấu hiệu cần kiểm tra.
3. **Kiểm tra đầu ra là Collection mới hay view**: new ArrayList, collect(toCollection) thường tạo container riêng; subList và unmodifiableList có thể là view.
4. **Kiểm tra element mutability**: copy nông có thể giữ chung đối tượng; setName bên trong mapper vẫn sửa object gốc.
5. **Kiểm tra API version và quyền sửa**: List.of/copyOf/toList có những đặc điểm khác ArrayList, và có từ các phiên bản Java khác nhau.
6. **Kiểm tra thread safety**: Collection đang được nhiều thread/parallelStream dùng? Có side effect lên dữ liệu chia sẻ không?
7. **Viết test chứng minh contract**: chụp nội dung source trước lời gọi, gọi method, so sánh source sau lời gọi và sửa riêng result để xem có lan truyền thay đổi cấu trúc không.

Đừng lấy một lần test trên ArrayList làm bằng chứng mọi implementation của interface Collection có cùng hành vi. Java Collections Framework có cả mutable collections, fixed-size lists, unmodifiable collections và views.

## 17. Luyện tập có lời giải

### Bài 1 — Lọc phần tử, vẫn cần nguồn nguyên vẹn

~~~java
List<String> source = new ArrayList<>(
        Arrays.asList("An", "Binh", "Chi"));
List<String> result = source.stream()
        .filter(s -> !s.equals("Binh"))
        .collect(Collectors.toCollection(ArrayList::new));
~~~

**Đáp án:** source vẫn [An, Binh, Chi], result là [An, Chi]. Result là ArrayList mới có thể sửa; không đổi cấu trúc nguồn.

### Bài 2 — removeIf hay filter khi phải xóa thật?

Nếu hàm có contract xóa các phần tử không hợp lệ khỏi chính List truyền vào, nên dùng **removeIf** (nếu List được phép sửa). Nếu contract yêu cầu trả danh sách hợp lệ mà không thay đổi input, dùng **filter + collect**. Hai cách không tương đương về side effect.

### Bài 3 — Unmodifiable view có phải snapshot?

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
~~~

**Đáp án:** view nhìn thấy [A, B] dù không thể gọi view.add. Vì view được hậu thuẫn bởi source, nó không phải snapshot độc lập.

### Bài 4 — Sao chép List có Person mutable đã là deep copy?

**Đáp án:** Chưa. **new ArrayList<>(people)** và **List.copyOf(people)** chỉ sao chép cấu trúc chứa các tham chiếu. Nếu cùng Person bị gọi setter, cả hai List quan sát được trạng thái mới. Muốn deep copy cần tạo Person mới phù hợp quy tắc nghiệp vụ, hoặc dùng kiểu dữ liệu bất biến.

### Bài 5 — Vì sao add lên stream.toList() thất bại?

**Đáp án:** **Stream.toList()** từ Java 16 trả List không hỗ trợ mutator, nên add ném UnsupportedOperationException. Nếu cần kết quả có thể sửa, dùng **collect(Collectors.toCollection(ArrayList::new))**.

### Bài 6 — Việc gọi subList có tự tạo danh sách riêng?

**Đáp án:** Không. **subList** trả view; set/remove/add qua view khi được hỗ trợ có thể sửa List nguồn. Muốn cắt một bản sao, dùng **new ArrayList<>(source.subList(a, b))**.

### Bài 7 — Trong Java 8 muốn có kết quả đã sắp xếp mà không sửa nguồn?

~~~java
List<String> sorted = source.stream()
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

**Đáp án:** source không bị sắp xếp tại chỗ. **List.sort** hoặc **Collections.sort** mới là các thao tác sửa source.

### Bài 8 — Có thể dựa vào ConcurrentModificationException để biết luôn khi nào sửa sai không?

**Đáp án:** Không. Fail-fast có tính best effort và không thay thế đồng bộ. Khi muốn xóa trong lúc duyệt, dùng **Iterator.remove** theo hợp đồng hoặc **removeIf**; khi muốn tạo kết quả riêng, dùng Stream và collector. Khi có concurrency thực, cần chọn cấu trúc dữ liệu/cơ chế đồng bộ phù hợp.

## 18. Tóm tắt

1. **Mutation thay đổi Collection được truyền vào**: add, removeIf, replaceAll, sort, put... Nếu dữ liệu được chia sẻ, các bên giữ cùng tham chiếu sẽ quan sát thay đổi.
2. **Stream.filter/map/sorted không tự sửa nguồn**; muốn Collection kết quả cần terminal operation như collect hoặc Stream.toList. Mapper có side effect vẫn có thể sửa object hoặc nguồn — phải tránh khi không được phép.
3. **new ArrayList<>(source)** và **Collectors.toCollection(ArrayList::new)** tạo cấu trúc kết quả riêng, có thể sửa, nhưng chỉ sao chép nông phần tử tham chiếu.
4. **Collections.unmodifiableList(source)** là view chỉ đọc, không phải snapshot; **List.subList** và **Map.keySet** cũng có thể liên kết với nguồn.
5. **List.copyOf** (Java 10+) cho snapshot không sửa được của cấu trúc; **Stream.toList** (Java 16+) cũng không sửa được nhưng có quy tắc null khác.
6. **Collectors.toList không bảo đảm mutability**; nếu cần chắc chắn có thể add/remove vào output, dùng toCollection với một loại List cụ thể.
7. Khi quyết định, làm rõ ownership, API contract, nhu cầu giữ dữ liệu gốc, shallow/deep copy, null, phiên bản Java, thread safety và chi phí bộ nhớ.

### Tài liệu chính thức còn áp dụng

- Java SE 25 — **Collection**: optional operations, unmodifiable views và hợp đồng Collection: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html
- Java SE 25 — **List**: sort, replaceAll, subList, List.of, List.copyOf: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html
- Java SE 25 — **Collections**: unmodifiableList, sort và các phương thức tiện ích: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html
- Java SE 25 — **Stream**: filter/map/sorted/toList, non-interference: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Java SE 25 — **Collectors**: toList, toCollection, toUnmodifiableList, toMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- Java SE 25 — **Map**: views và mutator methods: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html
