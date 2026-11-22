# Kiểu generic lồng nhau trong List và Map

## 1. Từ một phần tử đến một cấu trúc nhiều tầng

Một đối số kiểu của generic có thể chính là một kiểu generic khác. Vì vậy, phần tử trong danh sách không nhất thiết là một chuỗi hay một số: nó có thể là một danh sách; giá trị của một bản đồ ánh xạ cũng có thể là một danh sách hoặc một bản đồ khác.

Đó là **kiểu generic lồng nhau**. Các tầng kiểu mô tả hình dạng dữ liệu và giúp trình biên dịch kiểm tra thao tác ở từng tầng. Đây là cách dùng phổ biến trong Java hiện hành, chẳng hạn nhóm điểm theo lớp, nhóm đơn hàng theo khách hàng hoặc lưu các dòng dữ liệu.

| Kiểu khai báo | Đọc theo tầng | Tình huống phù hợp |
| --- | --- | --- |
| `List<List<Integer>>` | Danh sách các danh sách số nguyên | Nhiều dòng số, mỗi dòng có thể dài khác nhau |
| `Map<String, List<Integer>>` | Khóa chuỗi ánh xạ đến danh sách số nguyên | Mỗi tên nhóm có nhiều giá trị |
| `List<Map<String, String>>` | Danh sách các bản đồ khóa chuỗi, giá trị chuỗi | Nhiều dòng thuộc tính đơn giản |
| `Map<String, Map<String, Integer>>` | Mỗi khóa ngoài ánh xạ đến một bản đồ đếm | Số lượng theo khu vực rồi theo sản phẩm |

Đọc từ ngoài vào để hiểu cấu trúc; đọc từ trong ra để xác định kiểu của dữ liệu cuối cùng. `List<List<Integer>>` không phải mảng hai chiều và cũng không buộc các danh sách con có cùng kích thước.

Bài này dùng `java.util.List`, `ArrayList`, `Map` và `LinkedHashMap`. Các đoạn minh họa ngắn được đặt trong phương thức; phần chương trình đầy đủ bên dưới có đủ import và lệnh chạy với Java 17 trở lên.

## 2. List chứa các List

### Khai báo và tạo từng tầng

```java
List<List<Integer>> rows = new ArrayList<>();
rows.add(new ArrayList<>(List.of(1, 2)));
rows.add(new ArrayList<>(List.of(3)));

List<Integer> firstRow = rows.get(0);
Integer firstValue = firstRow.get(0);
```

`new ArrayList<>()` đầu tiên chỉ tạo **danh sách ngoài**. Khi ấy `rows.size()` bằng `0`; chưa có dòng nào để gọi `rows.get(0)`. Mỗi lần thêm một `new ArrayList<>(...)`, ta tạo một danh sách con riêng rồi đưa tham chiếu của nó vào danh sách ngoài.

Các biểu thức mang kiểu cụ thể như sau:

| Biểu thức | Kiểu tại thời điểm biên dịch |
| --- | --- |
| `rows` | `List<List<Integer>>` |
| `rows.get(0)` | `List<Integer>` |
| `rows.get(0).get(0)` | `Integer` |
| `rows.size()` | `int`, số danh sách con |
| `rows.get(0).size()` | `int`, số phần tử của danh sách con đầu tiên |

Muốn thêm một số vào dòng đầu tiên, dùng `rows.get(0).add(9)`. Gọi `rows.add(9)` không hợp lệ vì danh sách ngoài yêu cầu một `List<Integer>`, không phải một `Integer`.

Cần kiểm tra chỉ số ở đúng tầng. Danh sách ngoài có phần tử thứ nhất không bảo đảm danh sách con thứ nhất có phần tử thứ nhất. Cả hai lần `get(0)` đều có thể gây `IndexOutOfBoundsException` nếu tầng tương ứng rỗng.

### Duyệt đúng cấu trúc

```java
int total = 0;
for (List<Integer> row : rows) {
    for (Integer value : row) {
        total += value;
    }
}
```

Vòng ngoài lấy từng danh sách con; vòng trong lấy từng số. Số phần tử của cấu trúc là tổng kích thước các danh sách con, không phải chỉ `rows.size()`.

Nếu dữ liệu thật cần hình chữ nhật, phải tự kiểm tra các dòng có cùng độ dài. Generic chỉ kiểm tra kiểu phần tử; nó không kiểm tra quy tắc số dòng, số cột hay miền giá trị nghiệp vụ.

## 3. Map có giá trị là List

Với `Map<String, List<Integer>>`, mỗi khóa chỉ có một giá trị, nhưng **giá trị đó là cả một danh sách**. Đây là cách biểu diễn quan hệ một nhóm có nhiều phần tử.

```java
Map<String, List<Integer>> scores = new LinkedHashMap<>();
scores.put("A", new ArrayList<>(List.of(8, 9)));
scores.put("B", new ArrayList<>(List.of(7)));

List<Integer> groupA = scores.get("A");
Integer firstScore = groupA.get(0);
```

Các tầng kiểu:

```text
Map<String, List<Integer>>
    │           │
    │           └─ giá trị ứng với khóa là List<Integer>
    └─ khóa là String

scores.get("A")        → List<Integer>
scores.get("A").get(0) → Integer
```

`put("A", anotherList)` thay thế giá trị đang gắn với khóa `"A"`; nó không tự gộp hai danh sách. Khi muốn bổ sung điểm vào nhóm hiện có, cần thao tác trên danh sách của nhóm.

### Khóa chưa tồn tại và danh sách rỗng là hai trạng thái khác nhau

Trong ví dụ không lưu giá trị `null`, `scores.get("C")` trả về `null` vì khóa chưa tồn tại. Gọi tiếp `.add(...)` hoặc `.get(0)` trên kết quả đó sẽ gây `NullPointerException`.

Ngược lại, một khóa ánh xạ đến danh sách rỗng vẫn là khóa đang tồn tại. Khi đó có thể gọi `add` nếu danh sách cho phép thay đổi, nhưng `get(0)` sẽ gây `IndexOutOfBoundsException`.

Nếu hệ thống cho phép giá trị map là `null`, chỉ kiểm tra kết quả `get` không đủ phân biệt khóa vắng với khóa đang ánh xạ đến `null`; cần cân nhắc `containsKey`. Một hợp đồng đơn giản hơn cho cấu trúc nhóm là không lưu danh sách `null`.

### Tạo danh sách khi cần rồi thêm phần tử

```java
scores.computeIfAbsent("C", key -> new ArrayList<>()).add(10);
```

`computeIfAbsent` tìm giá trị của khóa. Nếu chưa có giá trị khác `null`, hàm được cung cấp tạo một `ArrayList<Integer>` mới, map lưu nó và trả về danh sách đó. Sau đó `add(10)` đưa điểm vào danh sách vừa nhận.

Trong ví dụ này, lambda tạo danh sách không trả về `null`. Nếu hàm tạo trả về `null`, phương thức không tạo ánh xạ mới và kết quả có thể vẫn là `null`.

Điều kiện quan trọng: map phải cho phép cập nhật khi cần thêm khóa, và danh sách kết quả phải cho phép `add`. Nếu một khóa hiện có đang giữ `List.of(1, 2)`, `computeIfAbsent` trả lại chính danh sách ấy; `.add(10)` vẫn ném `UnsupportedOperationException`. Phương thức này không tự biến danh sách không cho sửa thành danh sách có thể sửa.

Không dùng đoạn mã trên như bảo đảm an toàn đa luồng. `LinkedHashMap` và `ArrayList` trong bài dành cho truy cập một luồng hoặc có đồng bộ phù hợp; việc tạo nhóm và cập nhật danh sách con là hai mối quan tâm riêng.

### Duyệt cả khóa và danh sách

```java
for (Map.Entry<String, List<Integer>> entry : scores.entrySet()) {
    String group = entry.getKey();
    List<Integer> values = entry.getValue();
    System.out.println(group + "=" + values);
}
```

`Map.Entry<K, V>` là cặp khóa–giá trị của một ánh xạ. Thay `K = String`, `V = List<Integer>` sẽ có kiểu trong vòng lặp trên. Nếu chỉ cần các danh sách để tính tổng, có thể duyệt `scores.values()` thay vì lấy từng khóa rồi gọi lại `get`.

### List chứa Map và Map chứa Map

Cùng nguyên tắc đọc từng tầng có thể áp dụng cho hai dạng còn lại:

```java
List<Map<String, Integer>> weeklyCounts = List.of(
        Map.of("A", 2, "B", 1),
        Map.of("A", 3));
Map<String, Integer> firstWeek = weeklyCounts.get(0);
Integer groupACount = firstWeek.get("A");

Map<String, Map<String, Integer>> stock = new LinkedHashMap<>();
stock.computeIfAbsent("north", key -> new LinkedHashMap<>())
        .put("book", 12);
Map<String, Integer> northStock = stock.get("north");
Integer bookCount = northStock.get("book");
```

Đây là đoạn minh họa đặt trong một phương thức. `weeklyCounts.get(0)` trả về một `Map<String, Integer>`; `.get("A")` trên map đó mới trả về `Integer`. Với `stock`, lần `get` thứ nhất dùng khóa khu vực, lần thứ hai dùng khóa sản phẩm. Không lấy chỉ số nguyên của `List` để thay cho khóa chuỗi của `Map`.

Các đối tượng tạo bằng `List.of` và `Map.of` trong đoạn này không cho cập nhật, còn `stock` và các map con do lambda tạo ra có thể cập nhật. Nếu khu vực chưa có hoặc sản phẩm chưa có, phải xử lý việc thiếu dữ liệu ở đúng tầng trước khi đọc tiếp hay unboxing về `int`.

## 4. Chương trình chạy đầy đủ: nhóm, duyệt và sao chép

Lưu mã sau thành **`NestedGenericsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class NestedGenericsDemo {
    static Map<String, List<Integer>> snapshot(
            Map<String, List<Integer>> source) {
        Map<String, List<Integer>> result = new LinkedHashMap<>();
        for (Map.Entry<String, List<Integer>> entry : source.entrySet()) {
            result.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        scores.computeIfAbsent("A", key -> new ArrayList<>()).add(8);
        scores.get("A").add(9);
        scores.computeIfAbsent("B", key -> new ArrayList<>()).add(7);
        scores.get("A").add(10);

        int count = 0;
        int total = 0;
        for (Map.Entry<String, List<Integer>> entry : scores.entrySet()) {
            System.out.println(entry.getKey() + "=" + entry.getValue());
            for (Integer value : entry.getValue()) {
                count++;
                total += value;
            }
        }
        System.out.println("count=" + count + ", total=" + total);

        Map<String, List<Integer>> frozen = snapshot(scores);
        Map<String, List<Integer>> shallow = new LinkedHashMap<>(scores);
        shallow.get("A").add(6);
        System.out.println("source A=" + scores.get("A"));
        System.out.println("snapshot A=" + frozen.get("A"));

        try {
            frozen.get("A").add(5);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot rejects add");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all NestedGenericsDemo.java
java NestedGenericsDemo
```

Stdout chính xác:

```text
A=[8, 9, 10]
B=[7]
count=4, total=34
source A=[8, 9, 10, 6]
snapshot A=[8, 9, 10]
snapshot rejects add
```

`LinkedHashMap` được dùng để giữ thứ tự chèn các khóa trong ví dụ, nên dòng `A` xuất hiện trước dòng `B`. Không lấy thứ tự in quan sát được của `HashMap` làm cam kết cho chương trình.

Hàm `snapshot` tạo map mới, tạo các danh sách không cho thay đổi bằng `List.copyOf`, rồi cung cấp map qua lớp bọc không cho cập nhật. Map mới không được trao ra dưới một tham chiếu có thể sửa ở nơi khác. Vì các khóa `String` và phần tử `Integer` cũng bất biến, thay đổi các danh sách của `scores` không làm đổi các giá trị đã chụp ở đây.

Hàm giả định source và các danh sách khác `null`; `List.copyOf` cũng từ chối phần tử `null`. Đây là lựa chọn hợp đồng dữ liệu của ví dụ, không phải hạn chế chung của mọi cấu trúc generic lồng nhau.

## 5. Khả năng thay đổi được quyết định ở từng tầng

Kiểu `List<List<Integer>>` không cho biết danh sách ngoài hay danh sách con có hỗ trợ `add`, `set`, `remove` hay không. Cần xem từng đối tượng được tạo bằng cách nào.

```java
List<List<Integer>> outerFixed = List.of(new ArrayList<>());
outerFixed.get(0).add(1); // Hợp lệ: danh sách con có thể thay đổi.
// outerFixed.add(new ArrayList<>()); // UnsupportedOperationException.

List<List<Integer>> innerFixed = new ArrayList<>();
innerFixed.add(List.of(1, 2)); // Hợp lệ: danh sách ngoài có thể thay đổi.
// innerFixed.get(0).add(3); // UnsupportedOperationException.
```

Hai ví dụ là các câu lệnh minh họa, các dòng gây lỗi đã được chú thích. Cấm sửa tầng ngoài không đồng nghĩa với cấm sửa tầng trong. Ngược lại, danh sách con không cho sửa cũng không ngăn việc thêm hoặc bỏ cả một danh sách con khỏi tầng ngoài.

`final List<List<Integer>> rows` chỉ ngăn gán lại biến `rows`. Nó không tự ngăn sửa đối tượng mà biến trỏ tới.

Tương tự, `Map.copyOf(scores)` tạo map không cho cập nhật nhưng không tự sao chép sâu từng danh sách giá trị. `Collections.unmodifiableMap(scores)` cung cấp một góc nhìn không cho cập nhật map qua góc nhìn đó; thay đổi map gốc vẫn có thể xuất hiện, và các danh sách con vẫn là các đối tượng được dùng chung. Muốn chụp cấu trúc ổn định, phải xử lý từng tầng cần bảo vệ như hàm `snapshot`.

Nếu phần tử cuối là một đối tượng có thể thay đổi, sao chép danh sách vẫn giữ các tham chiếu tới đối tượng ấy. Khi đó cần quyết định sao chép đối tượng hoặc dùng mô hình dữ liệu bất biến; không gọi một bản sao danh sách là bản sao sâu của mọi dữ liệu.

## 6. Dùng chung tham chiếu và sao chép nông

### Một danh sách bị đưa vào nhiều vị trí

```java
List<Integer> shared = new ArrayList<>();
List<List<Integer>> rows = new ArrayList<>();
rows.add(shared);
rows.add(shared);
rows.get(0).add(5);
System.out.println(rows); // [[5], [5]]
```

Cả hai phần tử của `rows` trỏ tới **cùng một danh sách**. Hai vị trí không tạo thành hai bản sao. Để có hai dòng độc lập, tạo hai đối tượng riêng:

```java
List<List<Integer>> independent = new ArrayList<>();
independent.add(new ArrayList<>());
independent.add(new ArrayList<>());
```

Khi tạo nhiều nhóm bằng vòng lặp, đặt `new ArrayList<>()` bên trong vòng lặp nếu mỗi nhóm cần dữ liệu riêng.

### Constructor sao chép chỉ sao chép tầng đang xây dựng

`new ArrayList<>(rows)` tạo danh sách ngoài mới nhưng vẫn chứa các tham chiếu đến danh sách con cũ. `new LinkedHashMap<>(scores)` tạo map mới nhưng vẫn trỏ tới các danh sách giá trị cũ. Vì thế, trong chương trình đầy đủ, thêm `6` qua `shallow.get("A")` cũng làm thay đổi danh sách đọc qua `scores.get("A")`.

Muốn hai map có các danh sách giá trị độc lập và cùng cho phép sửa, có thể sao chép từng danh sách:

```java
Map<String, List<Integer>> copied = new LinkedHashMap<>();
for (Map.Entry<String, List<Integer>> entry : scores.entrySet()) {
    copied.put(entry.getKey(), new ArrayList<>(entry.getValue()));
}
```

Đoạn này sao chép cấu trúc map và các danh sách; nó không sao chép sâu các phần tử tùy ý. Với `Integer` bất biến, chia sẻ các đối tượng số không tạo lỗi thay đổi trạng thái phần tử.

## 7. Quan hệ kiểu phải xét ở mọi tầng

`Integer` là kiểu con của `Number`, nhưng `List<Integer>` không phải kiểu con của `List<Number>`. Lồng thêm một tầng không làm quy tắc đó biến mất:

```java
List<List<Integer>> integers = new ArrayList<>();
// List<List<Number>> numbers = integers; // Lỗi biên dịch.
// List<List<? extends Number>> views = integers; // Vẫn lỗi biên dịch.
```

Ở dòng cuối, các đối số của `List` ngoài là `List<Integer>` và `List<? extends Number>`. Chúng không phải cùng một kiểu; wildcard đặt ở tầng trong không làm tầng ngoài tự trở thành linh hoạt.

Một hàm chỉ cần đọc các số từ nhiều dòng có thể đặt wildcard đúng ở cả hai tầng:

```java
static double sumRows(List<? extends List<? extends Number>> rows) {
    double total = 0;
    for (List<? extends Number> row : rows) {
        for (Number value : row) {
            total += value.doubleValue();
        }
    }
    return total;
}
```

Đây là phương thức minh họa đặt trong một lớp. Nó nhận được `List<List<Integer>>` và `List<List<Double>>`. Wildcard ngoài cho phép nhận danh sách có kiểu phần tử là một kiểu con phù hợp của `List<? extends Number>`; wildcard trong cho phép đọc các kiểu số khác nhau dưới kiểu `Number`.

Phương thức trên giả định không có dòng hoặc phần tử `null`. `doubleValue()` còn có thể làm mất độ chính xác của một số kiểu số; đây là ví dụ về khả năng đọc theo kiểu, không phải công cụ tính toán chính xác cho mọi miền dữ liệu.

`? extends ...` giới hạn việc thêm dữ liệu do kiểu cụ thể chưa biết. Nó không biến danh sách thành đối tượng bất biến: những thao tác không cần cung cấp phần tử kiểu đó, như `clear()`, vẫn có thể được phép nếu đối tượng hỗ trợ. Muốn bảo đảm không thay đổi phải dùng hợp đồng và cách bọc/sao chép phù hợp, không chỉ dùng wildcard.

Tương tự, `Map<String, List<Integer>>` không tự gán được sang `Map<String, List<Number>>`. Khi viết API, xác định nó chỉ đọc, thêm phần tử hay thay cả danh sách trước khi chọn chữ ký; không ép kiểu để bỏ qua lỗi generic.

## 8. Khi nào cấu trúc lồng nhau trở nên khó đọc?

Một kiểu như `Map<String, Map<String, List<Integer>>>` có thể hợp lệ nhưng không nói rõ từng khóa mang ý nghĩa gì. Nếu người đọc liên tục phải nhớ khóa thứ nhất là khu vực hay lớp học, nên đặt tên biến/phương thức rõ hơn hoặc tạo lớp dữ liệu cho khái niệm nghiệp vụ.

Ví dụ, `List<Map<String, String>>` phù hợp khi các cặp thuộc tính thực sự linh hoạt. Nếu mỗi bản ghi luôn có tên và tuổi, một lớp `Student` thường giúp mô tả trường bắt buộc và giữ tuổi ở kiểu số. Không thêm tầng map chỉ để tránh khai báo một kiểu dữ liệu rõ nghĩa.

Các dấu `>>` ở cuối `List<List<Integer>>` đóng hai danh sách đối số kiểu. Không cần tách thành `> >` trong Java hiện hành. Dấu diamond `<>` giúp suy luận lúc khởi tạo, còn khai báo bên trái vẫn cần diễn đạt đúng cấu trúc mà API muốn cung cấp.

Khi dùng `var`, luôn kiểm tra kiểu được suy luận. Chẳng hạn `var rows = new ArrayList<>()` không có ngữ cảnh chỉ định kiểu phần tử nên suy luận thành `ArrayList<Object>`, không tự biết rằng ta muốn danh sách các danh sách số. Khai báo `List<List<Integer>> rows = new ArrayList<>()` làm ý định rõ ràng.

## 9. Thực hành kiểm tra hiểu biết

1. Tạo `List<List<Integer>>` gồm các dòng `[1, 2]`, `[]`, `[3]`. Viết vòng lặp tính số phần tử và tổng. Kết quả cần là `3` phần tử, tổng `6`; danh sách ngoài có `3` dòng.
2. Tạo `Map<String, List<String>>` lưu nhiều tên học viên theo nhóm. Dùng `computeIfAbsent` để thêm hai tên vào một nhóm mới mà không ghi đè tên trước.
3. Tạo hai khóa cùng trỏ tới một `ArrayList`, thay đổi danh sách qua một khóa và giải thích kết quả khi đọc qua khóa kia. Sau đó sửa thành hai danh sách độc lập.
4. Dùng hàm `snapshot` trong chương trình đầy đủ. Thử thay thế một ánh xạ của bản chụp và thử thêm vào danh sách con; cả hai thao tác thay đổi đều phải bị từ chối. Thay đổi source rồi xác nhận bản chụp giữ nguyên dữ liệu trước đó.
5. Giải thích vì sao `rows.size()`, `scores.size()` và tổng số phần tử bên trong có thể là ba đại lượng khác nhau.

Điểm cần nhớ khi thao tác là: mỗi lần `get` đi xuống đúng một tầng, mỗi tầng có kiểu và khả năng thay đổi riêng, còn phép sao chép một tầng không tự tạo bản sao cho các đối tượng bên dưới.

## Tài liệu đối chiếu

- [List — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): hợp đồng danh sách và các phương thức tạo/sao chép danh sách.
- [Map — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): ánh xạ khóa–giá trị, `get`, `put` và `computeIfAbsent`.
- [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): góc nhìn map không cho cập nhật.
- [JLS §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): đối số kiểu và wildcard.
