# Phân biệt Collection, Collections và Java Collections Framework

Khi đọc mã Java, ba tên này thường xuất hiện gần nhau nhưng chỉ ba phạm vi khác nhau:

- **`Collection<E>`** là một interface mô tả một nhóm phần tử và những thao tác chung trên nhóm đó.
- **`Collections`** là một lớp tiện ích cung cấp các phương thức `static` để thao tác với collection hoặc tạo các đối tượng bao bọc.
- **Java Collections Framework (JCF)** là hệ thống các interface, lớp triển khai, thuật toán và hợp đồng liên quan đến việc tổ chức, truy cập và xử lý các nhóm dữ liệu.

Ví dụ, trong câu “dùng `Collections.sort` để sắp xếp một `ArrayList` thuộc Java Collections Framework”, `Collections` là nơi chứa thuật toán, `ArrayList` là đối tượng chứa dữ liệu, còn framework là toàn bộ hệ thống mà các thành phần đó tham gia.

## 1. Vì sao cần phân biệt ba tên?

Giả sử ứng dụng cần lưu danh sách người đăng ký và tạo một bản được sắp xếp để hiển thị. Có ba câu hỏi khác nhau:

1. **Đối tượng cần cung cấp khả năng gì?** Có thể hỏi số phần tử, duyệt qua và kiểm tra sự có mặt của một tên hay không? Đây là câu hỏi về hợp đồng, chẳng hạn `Collection<E>`.
2. **Đối tượng tổ chức dữ liệu bằng cách nào?** Dùng danh sách `ArrayList`, tập hợp `LinkedHashSet` hay một cấu trúc khác? Đây là lựa chọn lớp triển khai.
3. **Có công cụ dùng chung nào xử lý dữ liệu?** Chẳng hạn sắp xếp danh sách hoặc đếm số lần một tên xuất hiện bằng các phương thức của `Collections`.

Framework kết nối các lựa chọn này. Nhờ các hợp đồng thống nhất, mã xử lý không phải viết lại cho từng lớp lưu trữ.

| Tiêu chí | `Collection<E>` | `Collections` | Java Collections Framework |
| --- | --- | --- | --- |
| Bản chất | Interface có tham số kiểu `E` | Lớp tiện ích | Một hệ thống API và quy ước thiết kế |
| Câu hỏi trả lời | Một nhóm phần tử cung cấp những thao tác chung nào? | Dùng công cụ nào để xử lý hoặc bao bọc collection? | Những thành phần này phối hợp với nhau ra sao? |
| Cách xuất hiện trong mã | `Collection<String> names` | `Collections.sort(names)` khi `names` có kiểu phù hợp | Không phải một kiểu để khai báo biến |
| Có tự chứa dữ liệu cụ thể không? | Interface không cung cấp cấu trúc lưu trữ cụ thể | Không phải đối tượng chứa các phần tử của người dùng | Bao gồm nhiều lớp chứa dữ liệu |
| Có thể gọi `new` trực tiếp không? | Không thể khởi tạo trực tiếp một interface | Không dùng `new Collections()` | Không có lớp tên `JavaCollectionsFramework` để khởi tạo |
| Ví dụ liên quan | `List`, `Set`, `Queue` kế thừa `Collection` | `sort`, `frequency`, `unmodifiableList` | `ArrayList`, `HashSet`, `HashMap`, các interface và thuật toán |

Tên lớp có thêm chữ **s** là `Collections`. Sự khác nhau không chỉ là số ít và số nhiều trong tiếng Anh, mà là khác nhau giữa **interface**, **lớp tiện ích** và **toàn bộ framework**.

## 2. Collection<E>: hợp đồng cho một nhóm phần tử

### 2.1. Interface khác lớp triển khai

`java.util.Collection<E>` biểu diễn một nhóm phần tử có kiểu `E`. Nó kế thừa `Iterable<E>`, vì vậy một collection có thể cung cấp iterator và được duyệt bằng vòng lặp `for-each`.

Đoạn mã minh họa sau đặt bên trong một phương thức, với các import tương ứng từ `java.util`:

```java
Collection<String> names = new ArrayList<>();
names.add("Lan");
names.add("An");

System.out.println(names.size());       // 2
System.out.println(names.contains("An")); // true
```

Trong khai báo đầu tiên:

- `Collection<String>` là **kiểu của biến tham chiếu**: mã sử dụng biến chỉ dựa vào những khả năng mà kiểu này công bố.
- `ArrayList<>` là **lớp của đối tượng được tạo**: nó quyết định cách lưu trữ và thực hiện thao tác.
- `String` là **kiểu phần tử** trong chương trình này.

Interface đóng vai trò hợp đồng; đối tượng `ArrayList` thực hiện hợp đồng đó thông qua `List`.

Không thể viết `new Collection<String>()` như cách khởi tạo một lớp cụ thể. Có thể tự triển khai interface, nhưng trong mã thông thường nên bắt đầu từ lớp triển khai phù hợp đã có trong JDK.

### 2.2. Những khả năng chung

Các thao tác quen thuộc ở mức `Collection` gồm:

| Nhóm thao tác | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Hỏi về kích thước | `size()`, `isEmpty()` | Xem số phần tử và collection có rỗng không |
| Hỏi về nội dung | `contains(value)`, `containsAll(other)` | Kiểm tra sự có mặt của phần tử |
| Thêm hoặc xóa | `add(value)`, `remove(value)`, `clear()` | Yêu cầu thay đổi các phần tử |
| Xử lý nhiều phần tử | `addAll(other)`, `removeAll(other)`, `retainAll(other)` | Thao tác với một nhóm phần tử |
| Duyệt hoặc chuyển dạng | `iterator()`, `toArray()`, `stream()` | Cung cấp cách đi qua hoặc xử lý dữ liệu |

Bảng này giúp nhận diện phạm vi của interface; không có nghĩa mọi đối tượng đều hỗ trợ mọi thao tác thay đổi.

Chẳng hạn, `Collection` có phương thức `add`, nhưng một danh sách được tạo bằng `List.of(...)` không cho thêm phần tử. Lời gọi vẫn hợp lệ về mặt kiểu, rồi bị từ chối lúc chạy bằng `UnsupportedOperationException`.

Ngoài ra, chỉ nhìn kiểu `Collection<E>` chưa đủ để kết luận:

- Các phần tử có được giữ theo thứ tự thêm vào hay không.
- Có cho phần tử trùng lặp hoặc `null` hay không.
- Có thể sửa nội dung hay không.
- Có an toàn khi nhiều luồng đồng thời truy cập và sửa hay không.
- Chi phí tra cứu hoặc thêm phần tử là bao nhiêu.

Những bảo đảm đó cần đọc ở interface cụ thể hơn và lớp triển khai đang dùng. Hợp đồng và các thao tác tùy chọn được mô tả trong [API Collection của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

### 2.3. Kiểu tham chiếu quyết định phương thức có thể gọi

Ví dụ sau vẫn là đoạn mã bên trong phương thức:

```java
Collection<String> names = new ArrayList<>(List.of("Lan", "An"));

// names.get(0); // Không biên dịch: Collection không khai báo get(int).
```

Đối tượng thực sự là `ArrayList`, nhưng biến `names` được khai báo là `Collection`. Trình biên dịch kiểm tra lời gọi dựa trên kiểu của biến.

Nếu yêu cầu cần truy cập theo vị trí, có thể khai báo bằng `List<String>`:

```java
List<String> names = new ArrayList<>(List.of("Lan", "An"));
System.out.println(names.get(0)); // Lan
```

Không nên khai báo `Collection` trong mọi tình huống chỉ vì nó tổng quát. Kiểu phải thể hiện đúng những khả năng mà đoạn mã cần dùng.

## 3. Collections: lớp tiện ích, không phải nơi chứa phần tử

### 3.1. Gọi phương thức static

`java.util.Collections` cung cấp các thuật toán và phương thức tiện ích. Cách dùng điển hình là gọi qua tên lớp:

```java
List<Integer> scores = new ArrayList<>(List.of(30, 10, 20, 10));

Collections.sort(scores);
System.out.println(scores); // [10, 10, 20, 30]

System.out.println(Collections.frequency(scores, 10)); // 2
```

Đây là đoạn mã minh họa trong phương thức, không phải chương trình độc lập.

`Collections.sort(scores)` tác động lên danh sách `scores` được truyền vào; lớp `Collections` không trở thành chủ sở hữu của một danh sách riêng chứa các điểm số.

Không viết:

```java
// Collections<String> names;       // Sai: Collections không phải kiểu generic này.
// Collections tools = new Collections(); // Sai: không khởi tạo lớp tiện ích này.
```

Một phương thức của `Collections` có thể có tham số kiểu generic riêng. Điều đó khác với việc bản thân lớp có khai báo `Collections<E>`.

### 3.2. Mỗi phương thức có yêu cầu đầu vào riêng

Không phải phương thức nào trong `Collections` cũng nhận một `Collection` bất kỳ.

| Ví dụ | Đầu vào điển hình | Điểm cần nhớ |
| --- | --- | --- |
| `Collections.frequency(c, x)` | `Collection<?>` | Đếm số phần tử bằng giá trị cần tìm |
| `Collections.sort(list)` | `List` có phần tử so sánh được theo yêu cầu | Sắp xếp chính danh sách truyền vào |
| `Collections.reverse(list)` | `List` hỗ trợ thay phần tử | Đảo thứ tự trong danh sách |
| `Collections.binarySearch(list, key)` | `List` đã được sắp xếp phù hợp | Không dùng trên dữ liệu chưa sắp xếp rồi tin kết quả |
| `Collections.unmodifiableList(list)` | `List` | Tạo một view không cho sửa qua tham chiếu trả về |
| `Collections.unmodifiableMap(map)` | `Map` | Cho thấy tiện ích của lớp này còn phục vụ nhánh `Map` |

Vì vậy, nếu biến có kiểu `Collection<String>`, không thể truyền thẳng nó cho `Collections.sort` chỉ vì đối tượng hiện tại là `ArrayList`. Một cách rõ ràng là tạo bản danh sách:

```java
Collection<String> source = new ArrayList<>(List.of("Lan", "An"));

List<String> sorted = new ArrayList<>(source);
Collections.sort(sorted);

System.out.println(source); // [Lan, An]
System.out.println(sorted); // [An, Lan]
```

Đoạn này tạo một danh sách mới chứa các tham chiếu phần tử từ `source`. Việc đổi thứ tự của danh sách mới không đổi thứ tự của danh sách gốc.

Cũng không nên gọi một thuật toán sửa danh sách trên đối tượng không hỗ trợ thao tác đó. Chẳng hạn, `Collections.sort(List.of(3, 1, 2))` sẽ ném `UnsupportedOperationException`. Có thể tạo `new ArrayList<>(...)` trước khi cần sửa.

Các điều kiện và tác động cụ thể thuộc hợp đồng của từng phương thức trong [API Collections của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

## 4. Java Collections Framework: bức tranh lớn hơn

Framework không phải một interface lớn tên `Collection`, cũng không chỉ là các phương thức trong lớp `Collections`.

Có thể nhìn nó qua các nhóm thành phần:

1. **Interface** mô tả các mô hình và khả năng: `Collection`, `List`, `Set`, `Queue`, `Deque`, `Map`...
2. **Lớp triển khai** cung cấp cách tổ chức dữ liệu: `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `ArrayDeque`, `HashMap`...
3. **Thuật toán và tiện ích** xử lý hoặc bao bọc các cấu trúc đó, tiêu biểu là lớp `Collections`.
4. **Các hợp đồng chung** giúp các thành phần phối hợp: cách duyệt phần tử, ý nghĩa của phép so sánh, điều kiện sửa đổi và những bảo đảm mà từng kiểu công bố.

Điểm có ích là tách nhu cầu sử dụng khỏi một cách lưu trữ cố định. Một phương thức chỉ cần duyệt các tên có thể nhận `Collection<String>`; bên gọi có thể cung cấp một `ArrayList<String>` hoặc một `LinkedHashSet<String>`, miễn đáp ứng hợp đồng mà phương thức cần.

### 4.1. Sơ đồ quan hệ rút gọn

Sơ đồ dưới dùng các interface quen thuộc trong Java 17; đây không phải toàn bộ cây API:

```text
Iterable<E>
└── Collection<E>
    ├── List<E>          ví dụ: ArrayList
    ├── Set<E>           ví dụ: HashSet, LinkedHashSet
    └── Queue<E>
        └── Deque<E>     ví dụ: ArrayDeque

Map<K, V>               ví dụ: HashMap, LinkedHashMap
                        là một nhánh riêng trong framework

Collections             lớp tiện ích phục vụ các kiểu phù hợp
```

Đọc sơ đồ theo quan hệ kế thừa của **interface**. Các tên lớp ở bên phải là ví dụ, không phải mỗi lớp chỉ có thể thực hiện đúng một interface. Chẳng hạn, `LinkedList` thực hiện cả `List` và `Deque`.

`Iterable` nằm ở `java.lang`; `Collection`, `Collections` và nhiều kiểu liên quan nằm ở `java.util`. Một hệ thống API có thể trải trên nhiều package; framework không đồng nghĩa với một package hay một câu lệnh `import` duy nhất.

Tài liệu [Collections Framework Overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html) là điểm vào để xem toàn bộ các thành phần và quan hệ của JCF.

### 4.2. Map thuộc framework nhưng không phải Collection

`Map<K, V>` biểu diễn ánh xạ từ khóa sang giá trị. Nó không kế thừa `Collection<E>`.

Lý do cần phân biệt về mô hình: một collection được nhìn như một nhóm phần tử, trong khi map được thao tác chủ yếu bằng quan hệ **khóa → giá trị**. Với map, có những câu hỏi riêng như “giá trị ứng với khóa này là gì?” hoặc “khóa này đã có ánh xạ chưa?”.

Từ một map, ta có thể lấy các view dạng collection:

| Phương thức | Kiểu kết quả | Nội dung |
| --- | --- | --- |
| `keySet()` | `Set<K>` | Các khóa |
| `values()` | `Collection<V>` | Các giá trị; có thể có giá trị lặp |
| `entrySet()` | `Set<Map.Entry<K, V>>` | Các cặp khóa–giá trị |

Các view này gắn với map gốc. Chúng không phải bản sao độc lập chỉ vì có kiểu `Collection` hoặc `Set`; những thay đổi được hỗ trợ phải được hiểu theo hợp đồng view.

Không thể kết luận “`HashMap` không thuộc JCF” chỉ vì nó không triển khai `Collection`. Cũng không thể gán một `HashMap` vào biến `Collection`. Quan hệ chính xác được công bố trong [API Map của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 5. Chương trình hoàn chỉnh để kiểm chứng

Lưu nguyên chương trình sau vào tệp **CollectionsOverviewDemo.java**. Chương trình dùng API tương thích Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionsOverviewDemo {
    public static void main(String[] args) {
        Collection<String> names =
                new ArrayList<>(List.of("Lan", "An", "Lan"));
        names.add("Binh");

        System.out.println("Collection: " + names);
        System.out.println("Size: " + names.size());
        System.out.println("Contains Lan: " + names.contains("Lan"));

        List<String> sorted = new ArrayList<>(names);
        Collections.sort(sorted);
        System.out.println("Sorted copy: " + sorted);
        System.out.println("Original: " + names);
        System.out.println("Lan count: " + Collections.frequency(names, "Lan"));

        Set<String> unique = new LinkedHashSet<>(names);
        System.out.println("Set: " + unique);

        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String name : names) {
            counts.merge(name, 1, Integer::sum);
        }
        System.out.println("Map: " + counts);
        Collection<Integer> values = counts.values();
        System.out.println("Map values: " + values);

        List<String> readOnly = Collections.unmodifiableList(sorted);
        sorted.add("Vy");
        System.out.println("Read-only view: " + readOnly);

        try {
            readOnly.add("Hoa");
        } catch (UnsupportedOperationException ex) {
            System.out.println("View add: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp, với một JDK hỗ trợ biên dịch cho Java 17:

```shell
javac --release 17 -encoding UTF-8 CollectionsOverviewDemo.java
java CollectionsOverviewDemo
```

Stdout:

```text
Collection: [Lan, An, Lan, Binh]
Size: 4
Contains Lan: true
Sorted copy: [An, Binh, Lan, Lan]
Original: [Lan, An, Lan, Binh]
Lan count: 2
Set: [Lan, An, Binh]
Map: {Lan=2, An=1, Binh=1}
Map values: [2, 1, 1]
Read-only view: [An, Binh, Lan, Lan, Vy]
View add: UnsupportedOperationException
```

### Đọc kết quả theo ba tầng

- **Hợp đồng:** biến `names` có kiểu `Collection<String>`, nên có thể gọi `add`, `size`, `contains` và dùng `for-each`.
- **Lớp triển khai:** đối tượng ban đầu là `ArrayList`, vì vậy ví dụ giữ thứ tự thêm và có hai phần tử `"Lan"`. `LinkedHashSet` loại phần tử lặp và giữ thứ tự thêm của các phần tử còn lại trong ví dụ.
- **Tiện ích:** `Collections.sort` sắp xếp bản `sorted`; `Collections.frequency` đếm hai lần xuất hiện của `"Lan"`; `Collections.unmodifiableList` tạo view không cho sửa.
- **Framework:** tất cả những thành phần đó, cùng nhánh `Map`, phối hợp trong một chương trình mà không cần một đối tượng “framework” đứng ra điều khiển.

Hai lớp có tiền tố `LinkedHash` được chọn để thứ tự in trong ví dụ có thể dự đoán. Không nên thay chúng bằng `HashSet` hoặc `HashMap` rồi mặc định stdout vẫn có cùng thứ tự.

## 6. View không cho sửa khác bản sao bất biến

Trong chương trình:

```java
List<String> readOnly = Collections.unmodifiableList(sorted);
sorted.add("Vy");
```

`readOnly` không cho gọi `add` để sửa danh sách **qua view đó**, nhưng nó vẫn đọc dữ liệu từ danh sách `sorted`. Khi `sorted` được thêm `"Vy"`, view cũng nhìn thấy phần tử mới. Lời gọi `readOnly.add("Hoa")` bị từ chối và được bắt trong ví dụ để chương trình tiếp tục kết thúc bình thường.

Phân biệt ba câu hỏi:

1. Có được sửa qua tham chiếu đang cầm không?
2. Nội dung có thể đổi qua một tham chiếu khác không?
3. Bản thân các đối tượng phần tử có thể bị sửa không?

Một lớp bao bọc không cho sửa không tự trả lời “không” cho cả ba câu hỏi. Ngay cả khi đã tạo bản sao cấu trúc danh sách, các phần tử bên trong vẫn có thể là cùng các đối tượng có thể thay đổi.

Chi tiết này quan trọng khi đọc tên các phương thức trong `Collections`: phải hiểu đối tượng trả về là view, bản sao hay kết quả thuật toán, thay vì suy ra hành vi từ tên gọi chung chung.

## 7. Chọn đúng kiểu khi thiết kế mã

Bắt đầu từ yêu cầu, rồi chọn kiểu biểu đạt yêu cầu đó:

| Yêu cầu | Kiểu thường phù hợp |
| --- | --- |
| Chỉ cần xử lý một nhóm phần tử bằng các thao tác chung | `Collection<E>` |
| Cần vị trí, thứ tự danh sách và truy cập bằng chỉ số | `List<E>` |
| Cần thể hiện yêu cầu không có phần tử lặp | `Set<E>` |
| Cần lấy giá trị theo khóa | `Map<K, V>` |
| Cần xử lý phần tử theo chính sách hàng đợi | `Queue<E>` hoặc kiểu cụ thể hơn |
| Cần thuật toán dùng chung | Tìm phương thức phù hợp của `Collections`, hoặc API trên kiểu dữ liệu |

Một tham số kiểu `Collection<String>` chỉ nói về hợp đồng được chấp nhận. Nó không tự bảo đảm đầu vào có thể sửa, không rỗng hoặc không chứa `null`. Nếu phương thức cần những điều kiện đó, phải nêu rõ hợp đồng và xử lý phù hợp.

Lớp triển khai vẫn cần được chọn theo dữ liệu và thao tác thực tế. Cùng thuộc JCF không có nghĩa `ArrayList`, `HashSet` và `HashMap` có cùng ngữ nghĩa, chi phí hay mức an toàn đồng thời.

## 8. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| “Collection và Collections là hai cách viết của một thứ” | Một bên là interface; một bên là lớp tiện ích |
| “Collections chứa dữ liệu của ứng dụng” | Dữ liệu nằm trong các đối tượng được truyền vào hoặc được phương thức trả về |
| “Mọi lớp trong framework đều kế thừa Collection” | Nhánh `Map` là phản ví dụ quan trọng |
| “Có phương thức add thì chắc chắn thêm được” | Thao tác thay đổi có thể không được hỗ trợ |
| “Collection nào cũng có thứ tự và truy cập bằng chỉ số” | Phải dựa vào kiểu cụ thể hơn; `Collection` không có `get(int)` |
| “Các tiện ích Collections luôn tạo bản sao” | Nhiều thuật toán sửa đầu vào; nhiều phương thức trả về view |
| “unmodifiable nghĩa là mọi dữ liệu sẽ bất biến” | Cần xem dữ liệu nền và tính có thể thay đổi của phần tử |
| “Thuộc JCF nghĩa là tự động an toàn luồng” | Phải kiểm tra bảo đảm của lớp, đối tượng bao bọc và cách sử dụng |

## 9. Tự kiểm tra

1. Trong `Collection<String> names = new ArrayList<>();`, đâu là interface và đâu là lớp triển khai?
2. Vì sao `Collections.sort(names)` không biên dịch nếu `names` chỉ có kiểu khai báo `Collection<String>`?
3. `Map<String, Integer>` có thuộc Java Collections Framework không? Nó có phải `Collection` không?
4. Sau khi tạo `Collections.unmodifiableList(list)`, nếu sửa `list` gốc thì view có đổi không?
5. Nếu một API yêu cầu truy cập theo chỉ số, vì sao `List<E>` diễn đạt yêu cầu tốt hơn `Collection<E>`?

Gợi ý đối chiếu: câu 1 và 2 liên quan đến kiểu tham chiếu; câu 3 liên quan đến phạm vi framework; câu 4 liên quan đến view; câu 5 liên quan đến hợp đồng mà mã sử dụng cần.
