# Phân biệt giá trị bằng nhau với cùng tham chiếu

Hai biến có thể trỏ đến cùng một đối tượng. Hai đối tượng khác nhau cũng có thể biểu diễn cùng một giá trị hoặc cùng một định danh nghiệp vụ. Đây là hai quan hệ khác nhau, và Java cung cấp những cơ chế khác nhau để diễn đạt chúng.

Trong collection, nhầm hai quan hệ này có thể dẫn đến những câu hỏi khó hiểu: vì sao `contains` tìm được một đối tượng chưa từng được thêm, vì sao `HashSet` chỉ còn một phần tử, hoặc vì sao hai danh sách in giống nhau nhưng phép so sánh cho kết quả khác?

Bài dùng Java 17, tập trung vào cách phân biệt danh tính đối tượng với bình đẳng logic, rồi áp dụng vào phần tử, khóa và chính collection. Chương trình đầy đủ cùng lệnh chạy và output nằm ở phần thực nghiệm. Các đoạn Java ngắn khác chỉ minh họa theo ngữ cảnh.

## 1. Hai câu hỏi phải tách biệt

Giả sử có hai đối tượng sản phẩm cùng mã `P1`.

Câu hỏi thứ nhất:

> Hai biến này có đang trỏ đến đúng cùng một đối tượng được tạo trong chương trình không?

Đây là bình đẳng tham chiếu. Với hai toán hạng tham chiếu có kiểu phù hợp để so sánh, ta dùng `==`.

Câu hỏi thứ hai:

> Theo quy tắc của lớp hoặc mô hình dữ liệu, hai đối tượng này có được coi là bằng nhau không?

Đây là bình đẳng logic, thường được diễn đạt bằng `equals`.

Hai câu hỏi có thể cho kết quả khác nhau mà không có lỗi. Cần xác định điều muốn hỏi trước khi chọn toán tử hoặc phương thức.

| Tình huống | Cùng tham chiếu? | Có thể bằng nhau theo giá trị? |
| --- | --- | --- |
| Gán `b = a` và chưa gán lại biến nào | Có | Có, với hợp đồng equals đúng trên đối tượng không null |
| Tạo hai chuỗi khác đối tượng nhưng cùng nội dung | Không | Có |
| Tạo hai sản phẩm khác đối tượng, cùng mã được lớp dùng làm tiêu chí bằng nhau | Không | Có |
| Tạo hai đối tượng không cùng tiêu chí bằng nhau | Không | Không |

“Bằng nhau theo giá trị” không tự có nghĩa mọi trường bên trong đều giống hệt. Nó phải được hiểu theo hợp đồng của lớp; một lớp có thể chọn một tập thuộc tính cụ thể để xác định bình đẳng.

## 2. Tham chiếu và phép gán biến

Xét đoạn minh họa:

```java
Product first = new Product("P1", "Pen");
Product alias = first;
```

Sơ đồ:

```text
first ----+
          |
          v
        mot doi tuong Product P1
          ^
          |
alias ----+
```

Phép gán không sao chép đối tượng. Nó chép giá trị tham chiếu, khiến hai biến cùng trỏ đến một đối tượng.

Vì vậy, `first == alias` là `true`.

Nếu tiếp tục:

```java
alias = new Product("P1", "Pen");
```

thì `alias` chuyển sang một đối tượng khác. `first` vẫn trỏ đến đối tượng ban đầu. Nếu lớp coi hai sản phẩm cùng mã là bằng nhau, lúc này:

- `first == alias` là `false`.
- `first.equals(alias)` có thể là `true`.

Không dùng cụm “cùng địa chỉ bộ nhớ” như một cam kết về địa chỉ vật lý mà chương trình Java có thể quan sát. Điều toán tử kiểm tra là danh tính tham chiếu theo mô hình ngôn ngữ; vị trí vật lý của đối tượng là chi tiết quản lý bộ nhớ.

## 3. == mang ý nghĩa khác theo kiểu toán hạng

### 3.1. Với hai tham chiếu

Phép so sánh tham chiếu cho `true` khi:

- Hai tham chiếu cùng chỉ một đối tượng.
- Hoặc cả hai đều là `null`.

Một tham chiếu null và một tham chiếu không null không bằng nhau theo phép này.

Việc viết được phép so sánh còn phụ thuộc kiểu tĩnh của hai toán hạng. Không phải mọi cặp lớp không liên quan đều có thể đem so sánh bằng `==` trong bất kỳ biểu thức nào.

### 3.2. Với kiểu nguyên thủy

`==` trên các giá trị nguyên thủy phù hợp kiểm tra giá trị theo quy tắc của toán hạng, bao gồm các chuyển đổi số khi áp dụng.

Không lấy câu “`==` so sánh tham chiếu” làm định nghĩa cho mọi trường hợp Java. Câu đó chỉ áp dụng khi phép toán đang là so sánh tham chiếu.

### 3.3. Wrapper có thể làm biểu thức khó nhìn

Nếu cả hai toán hạng là `Integer`, `==` có thể đang so sánh tham chiếu. Nếu một phía là `int`, biểu thức số có thể yêu cầu unboxing để so sánh giá trị.

Do đó, khi gặp một phép so sánh số có wrapper, phải xem kiểu của cả hai phía. Unboxing `null` còn có thể gây `NullPointerException`.

Quy tắc chi tiết nằm trong [JLS 17, Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).

## 4. equals không tự biết thế nào là bằng nhau về nghiệp vụ

### 4.1. Hành vi mặc định của Object

Nếu một lớp không override `equals`, nó nhận hành vi mặc định từ `Object`: với tham chiếu không null, hai đối tượng được coi là bằng nhau theo phương thức này khi cùng là một đối tượng.

Ví dụ hai đối tượng thuộc một lớp chỉ chứa trường `code`:

```java
PlainProduct a = new PlainProduct("P1");
PlainProduct b = new PlainProduct("P1");
```

Nếu lớp không override `equals`, `a.equals(b)` là `false`. Việc các trường được in ra giống nhau không khiến Java tự sinh quy tắc bình đẳng.

### 4.2. Override diễn đạt lựa chọn của mô hình

Một lớp có thể coi sản phẩm cùng mã là bằng nhau. Một kiểu giá trị khác có thể yêu cầu cả mã, đơn vị và phiên bản đều giống nhau.

Không có quy tắc chung rằng mọi lớp phải so sánh tất cả trường. Cần xác định:

1. Đối tượng đại diện cho điều gì?
2. Những thuộc tính nào quyết định việc hai biểu diễn có thể thay thế cho nhau trong mục đích đang xét?
3. Những thuộc tính đó có ổn định trong vòng đời sử dụng không?
4. Quy tắc có nhất quán với các collection và phép băm không?

### 4.3. Tên phương thức chưa đủ: phải đúng chữ ký

Chữ ký override đúng là:

```java
@Override
public boolean equals(Object other) {
    return other instanceof Product that && code.equals(that.code);
}
```

Đây là đoạn phương thức đặt trong lớp Product có trường code bắt buộc không null và lớp không cho kế thừa. Chương trình đầy đủ bên dưới trình bày cả lớp, hashCode và cách dùng.

Viết `boolean equals(Product other)` tạo một overload, không override `Object.equals(Object)`. Khi framework gọi theo chữ ký nhận `Object`, nó có thể không dùng phương thức mà người viết tưởng đã thay thế.

Dùng `@Override` giúp compiler phát hiện chữ ký không thực sự override như dự định.

### 4.4. Hợp đồng cơ bản phải giữ

Một `equals` đúng cần có các tính chất trên đối tượng không null:

- Phản xạ: đối tượng bằng chính nó.
- Đối xứng: đổi thứ tự so sánh không đổi kết luận.
- Bắc cầu: nếu a bằng b và b bằng c, thì a bằng c.
- Nhất quán khi dữ liệu liên quan không đổi.
- So với `null` trả `false`.

Các tính chất cùng yêu cầu liên quan `hashCode` được mô tả trong [Object.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

## 5. String: ví dụ rõ nhất về hai đối tượng cùng giá trị

Đoạn minh họa:

```java
String first = new String("java");
String second = new String("java");
```

Hai biểu thức `new` tạo hai đối tượng chuỗi khác nhau, nên:

```text
first == second       -> false
first.equals(second)  -> true
```

`String.equals` so sánh nội dung chuỗi theo hợp đồng của lớp. Nó không yêu cầu hai biến dùng cùng một đối tượng.

### 5.1. Literal và intern có thể che giấu lỗi

Hai literal chuỗi cùng nội dung có thể dùng cùng đối tượng đã intern theo quy tắc ngôn ngữ. Điều đó khiến một phép `==` tình cờ cho kết quả người viết đang muốn về giá trị.

Nhưng chuỗi lấy từ đầu vào, tệp, phép dựng hoặc nguồn khác không phải lúc nào cũng cùng tham chiếu với literal. Vì vậy, dùng `==` để kiểm tra nội dung chuỗi là sai mục đích, dù vài trường hợp nhỏ cho `true`.

Không cần gọi `new String(...)` trong mã thực tế chỉ để tránh dùng chung. Bài dùng nó để tạo thí nghiệm phân biệt hai quan hệ một cách rõ ràng.

### 5.2. Bằng nhau theo phương thức nào?

`"Java"` và `"java"` không bằng nhau theo `String.equals`.

Nếu một quy trình cần đối chiếu không phân biệt hoa thường hoặc theo quy tắc chuẩn hóa riêng, phải chọn phép đối chiếu phù hợp. Không suy ra cùng cách hiển thị hoặc cùng ý nghĩa ngôn ngữ là điều `String.equals` tự bảo đảm.

Hợp đồng ở [String.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#equals(java.lang.Object)).

## 6. Xử lý null khi so sánh giá trị

### 6.1. Gọi phương thức trên null là lỗi

Đoạn:

```java
Product a = null;
a.equals(other);
```

ném `NullPointerException` trước khi có thể dùng logic bình đẳng của `Product`.

Ngược lại, một đối tượng không null có `equals` đúng phải trả `false` khi nhận `null`.

### 6.2. Objects.equals diễn đạt kiểm tra dung nạp null

Có thể dùng:

```java
boolean equal = Objects.equals(a, b);
```

Quy tắc thông thường của phương thức:

| a | b | Kết quả |
| --- | --- | --- |
| `null` | `null` | `true` |
| `null` | Không null | `false` |
| Không null | `null` | `false` với equals đúng |
| Không null | Không null | Dựa vào bình đẳng của đối tượng theo hợp đồng |

`Objects.equals` không phản chiếu tất cả các trường để tự tìm một định nghĩa bình đẳng mới. Nó cũng không sửa được một lớp có `equals` sai đối xứng hoặc sai bắc cầu.

Xem [Objects.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

### 6.3. Null an toàn về kỹ thuật chưa chắc đúng nghiệp vụ

Hai giá trị cùng `null` có thể được `Objects.equals` coi là bằng nhau. Tuy nhiên, nếu mã sản phẩm là bắt buộc, hai sản phẩm đều thiếu mã không nên được âm thầm coi là hợp lệ chỉ nhờ biểu thức này.

Thiết kế constructor hoặc bước kiểm tra dữ liệu cần bảo vệ điều kiện nghiệp vụ. Trong chương trình đầy đủ, mã sản phẩm không được phép null.

## 7. Vì sao collection có thể tìm được một đối tượng khác tham chiếu?

Giả sử `Product` coi hai sản phẩm cùng mã là bằng nhau:

```java
Product stored = new Product("P1", "Pen");
Product query = new Product("P1", "Blue pen");

List<Product> products = new ArrayList<>();
products.add(stored);
```

Mặc dù `stored != query`, lời gọi:

```java
products.contains(query);
```

có thể trả `true` vì danh sách tìm thấy một phần tử bằng giá trị theo hợp đồng, chứ không chỉ tìm đúng tham chiếu `query`.

Tương tự, `products.remove(query)` có thể xóa phần tử được lưu dù đối tượng được truyền vào chưa từng được thêm.

### 7.1. Mục đích của tiêu chí bình đẳng

Nếu yêu cầu nghiệp vụ là tìm sản phẩm theo mã, đây có thể là hành vi mong muốn.

Nếu cần xóa đúng một đối tượng cụ thể trong một đồ thị đối tượng, bình đẳng theo mã có thể chưa phù hợp. Khi đó phải diễn đạt nhu cầu danh tính một cách rõ ràng, không đổi tùy tiện `equals` của cả lớp chỉ để phục vụ một thao tác đặc biệt.

### 7.2. Phần tử lặp trong List

Một list vẫn có thể chứa hai phần tử bằng nhau theo `equals`. `List` cho phép lặp; bình đẳng không tự loại phần tử khi thêm vào list.

Một lời gọi `remove(Object)` trên danh sách thông thường chỉ xóa một phần tử phù hợp theo hợp đồng, không xóa mọi đối tượng bằng nhau. Đừng nhầm quy tắc “bằng nhau” với chính sách số lần xuất hiện.

## 8. HashSet và HashMap: equals phải đi cùng hashCode

### 8.1. Hai đối tượng bằng nhau có thể là một phần tử tập hợp

Một `HashSet<Product>` có thể chỉ giữ một phần tử khi thêm hai đối tượng khác tham chiếu nhưng bằng nhau theo `equals` và có `hashCode` nhất quán.

Nó đang biểu diễn tập các giá trị phân biệt theo quy tắc của phần tử, không phải tập mọi lần gọi `new`.

### 8.2. Hai khóa bằng nhau có thể là cùng một ánh xạ

Với `HashMap<Product, Integer>`:

```java
map.put(first, 10);
map.put(second, 20);
```

nếu hai khóa bằng nhau theo hợp đồng và băm nhất quán, map quản lý một ánh xạ cho khóa đó; lần `put` sau thay giá trị tương ứng.

Không suy ra kích thước map bằng số đối tượng khóa đã được tạo hoặc bằng số lời gọi `put`.

### 8.3. Mã băm không phải căn cước duy nhất

Hợp đồng yêu cầu:

```text
a.equals(b) là true
    => a.hashCode() == b.hashCode()
```

Chiều ngược lại không đúng. Hai đối tượng không bằng nhau vẫn có thể trùng mã băm.

Cũng không được dùng `System.identityHashCode` như mã định danh duy nhất tuyệt đối cho mọi đối tượng. Mã băm danh tính vẫn có thể trùng; nó không thay thế phép so sánh tham chiếu.

### 8.4. Đừng nhìn toString để chứng minh danh tính

Hai đối tượng có thể có cùng chuỗi hiển thị nhưng không bằng nhau, hoặc bằng nhau theo một tập trường chọn lọc nhưng chuỗi hiển thị khác nhau.

Dạng mặc định như `ClassName@...` cũng không phải một địa chỉ bộ nhớ được bảo đảm. Không lấy output hiển thị làm hợp đồng `equals` hoặc `==`.

## 9. Chọn tiêu chí bình đẳng cho lớp tự định nghĩa

### 9.1. Bình đẳng phải phản ánh ý nghĩa đối tượng

Trong ví dụ `Product`, mã `code` quyết định bình đẳng, còn nhãn `label` không tham gia. Hai đối tượng cùng mã nhưng nhãn khác vẫn bằng nhau theo lựa chọn đó.

Điều này phù hợp với mô hình coi mã là định danh ổn định của sản phẩm. Nếu mô hình đang biểu diễn một bản chụp đầy đủ cần phân biệt cả nhãn, phải chọn quy tắc khác.

Không sao chép công thức từ ví dụ vào mọi lớp mà không xác định ý nghĩa dữ liệu.

### 9.2. Dữ liệu tham gia bình đẳng nên ổn định

Nếu một đối tượng đang làm phần tử trong tập băm hoặc làm khóa map, sửa trường tham gia `equals` hoặc `hashCode` có thể làm các thao tác tra cứu không còn đáp ứng giả định.

Có thể sửa nhãn hiển thị mà không đổi bình đẳng nếu nhãn không tham gia tiêu chí. Nhưng chính sách đó cần được thiết kế từ đầu.

Lựa chọn thường dễ quản lý là khóa có giá trị ổn định hoặc kiểu giá trị bất biến cho phần dùng trong băm.

### 9.3. Kế thừa cần được cân nhắc

Lớp con có thêm trạng thái có thể làm việc giữ đối xứng, bắc cầu của `equals` trở nên khó hơn nếu lớp cha và lớp con áp dụng tiêu chí khác nhau.

Chương trình dùng lớp `final` để giới hạn phạm vi so sánh và tránh đưa thêm vấn đề kế thừa vào ví dụ chính. Đây là lựa chọn của ví dụ, không phải quy tắc mọi lớp Java đều phải `final`.

### 9.4. Record hỗ trợ một quy tắc mặc định, không quyết định mọi nghiệp vụ

Record sinh hành vi bình đẳng dựa trên cùng lớp record và các thành phần theo hợp đồng của record. Điều đó thuận tiện cho nhiều kiểu dữ liệu giá trị.

Nhưng:

- Mọi thành phần được chọn làm trạng thái record đều có vai trò trong quy tắc mặc định.
- Thành phần tham chiếu vẫn dùng bình đẳng tương ứng của kiểu đó.
- Thành phần là mảng không tự được so sánh sâu theo nội dung chỉ vì nằm trong record.

Vẫn cần thiết kế thành phần phù hợp ý nghĩa miền. Xem [Record Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

## 10. Hai collection có thể khác đối tượng nhưng bằng nhau

Bây giờ không chỉ so sánh phần tử; chính list hoặc set cũng là đối tượng có `equals`.

### 10.1. List: cùng thứ tự và từng cặp phần tử bằng nhau

Hai list có thể thuộc hai lớp triển khai khác nhau:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = new LinkedList<>(List.of("A", "B"));
```

`a == b` là `false`, còn `a.equals(b)` là `true`.

Hợp đồng list xét kích thước và các cặp phần tử theo đúng thứ tự. Vì vậy:

```text
[A, B] khác [B, A]
[A, A, B] khác [A, B]
```

Không thay phép `equals` bằng `containsAll` nếu mục tiêu là bình đẳng danh sách, vì `containsAll` không diễn đạt thứ tự hoặc số lần xuất hiện theo cách đó.

Xem [List.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).

### 10.2. Set: cùng các phần tử theo hợp đồng tập hợp

Một `HashSet` chứa `A, B` và một `LinkedHashSet` chứa `B, A` có thể bằng nhau theo hợp đồng `Set`, dù thứ tự duyệt khác.

Tập hợp không coi thứ tự duyệt là một phần của bình đẳng tổng quát của set. Phần tử vẫn phải có quan hệ bình đẳng đúng và nhất quán.

Xem [Set.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).

### 10.3. Map: cùng các ánh xạ

Hai map thông thường có thể bằng nhau nếu biểu diễn cùng các ánh xạ khóa–giá trị theo hợp đồng `Map`, dù lớp triển khai hoặc thứ tự duyệt khác.

So sánh map không phải chỉ so tập khóa hoặc chỉ so các giá trị. Ánh xạ khóa nào gắn với giá trị nào mới là dữ liệu cần xét.

Xem [Map.equals Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

### 10.4. Không suy ra mọi Collection đều có equals theo phần tử

`Collection` không cung cấp một công thức bình đẳng nội dung dùng chung bắt buộc cho mọi cấu trúc.

Một ví dụ cụ thể là `ArrayDeque`: hai deque khác nhau có cùng phần tử theo cùng thứ tự vẫn không được phương thức `equals` của lớp coi là bằng nhau theo nội dung.

Nếu cần so sánh một hàng đợi theo trình tự phần tử, phải chọn quy trình hoặc biểu diễn so sánh phù hợp, thay vì mặc nhiên gọi `equals` và áp dụng quy tắc của list.

Tài liệu [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) lưu ý các cách triển khai hàng đợi thường không định nghĩa `equals` và `hashCode` dựa trên phần tử.

## 11. Mảng cần các phép so sánh nội dung riêng

### 11.1. equals của mảng không tự duyệt phần tử

Đoạn minh họa:

```java
int[] a = {1, 2};
int[] b = {1, 2};
```

Vì đây là hai đối tượng mảng khác nhau:

- `a == b` là `false`.
- `a.equals(b)` cũng là `false`.

Muốn so sánh nội dung một chiều, dùng `Arrays.equals(a, b)`, kết quả là `true`.

### 11.2. Mảng lồng và deepEquals

Với:

```java
Object[] a = {new int[]{1, 2}};
Object[] b = {new int[]{1, 2}};
```

`Arrays.equals(a, b)` kiểm tra các phần tử ở tầng ngoài theo bình đẳng tương ứng. Hai phần tử đó là hai mảng `int[]` khác tham chiếu, nên kết quả là `false`.

`Arrays.deepEquals(a, b)` xử lý nội dung mảng lồng theo hợp đồng và trả `true` trong ví dụ.

Không hiểu “deep” là tự phản chiếu và so tất cả trường của mọi lớp tùy ý. Với các phần tử đối tượng thông thường, bình đẳng của chính đối tượng vẫn có vai trò.

Xem [Arrays Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).

### 11.3. List chứa mảng vẫn cần xét bình đẳng của phần tử mảng

Nếu hai list chứa các mảng riêng biệt có cùng nội dung, hợp đồng list không tự biến bình đẳng của mảng thành so sánh sâu.

Đây là ví dụ cho nguyên tắc: bình đẳng của collection dựa vào bình đẳng phần tử; nó không sửa thay một quy tắc phần tử chưa phù hợp yêu cầu.

## 12. Khi nào thật sự cần danh tính tham chiếu?

Không phải mọi cách dùng `==` trên đối tượng đều sai.

### 12.1. Theo dõi đúng một đối tượng

Các tình huống có thể cần danh tính:

- Phát hiện hai biến có phải alias của cùng đối tượng.
- Theo dõi các nút đã thăm trong đồ thị đối tượng khi các nút có thể bằng giá trị.
- Giữ quan hệ chia sẻ đối tượng khi sao chép đồ thị.
- Quản lý dữ liệu phụ gắn với đúng một instance.

Ở những tình huống đó, gộp hai đối tượng chỉ vì `equals` trả `true` có thể làm sai thuật toán.

### 12.2. IdentityHashMap là cấu trúc chuyên dụng

`IdentityHashMap` so sánh khóa theo tham chiếu thay cho bình đẳng đối tượng thông thường. Hai khóa khác tham chiếu nhưng cùng giá trị logic có thể được giữ thành hai ánh xạ.

Đây là chủ đích của cấu trúc chuyên dụng, không phải một phiên bản `HashMap` có thể thay thế tùy ý. Nó cố ý khác hợp đồng map tổng quát về quan hệ bình đẳng.

Chọn nó khi thuật toán thật sự cần danh tính. Không dùng nó để che việc `equals` hoặc `hashCode` của khóa chưa được thiết kế đúng.

Xem [IdentityHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

### 12.3. Danh tính đối tượng khác với định danh nghiệp vụ

Hai đối tượng Java cùng biểu diễn một sản phẩm có mã `P1` không nhất thiết cùng một instance.

Cụm “cùng sản phẩm” có thể nói về mã nghiệp vụ, trong khi “cùng đối tượng” nói về tham chiếu. Khi trao đổi trong nhóm hoặc đặt tên biến, nên nói rõ lớp nghĩa đang xét.

## 13. Bằng nhau không chứng minh có hoặc không chia sẻ trạng thái

### 13.1. Hai đối tượng bằng giá trị có thể độc lập

Hai đối tượng bất biến có cùng giá trị có thể được tạo riêng. `equals` trả `true` không chứng minh sửa ở một phía sẽ tác động phía kia.

### 13.2. Hai collection khác tham chiếu có thể dùng chung phần tử

`new ArrayList<>(source)` tạo list khác nhưng thường sao chép các tham chiếu phần tử.

Hai list có thể vừa khác tham chiếu, vừa bằng nhau theo nội dung, đồng thời vẫn dùng chung các đối tượng phần tử. Nếu phần tử có thể thay đổi, đó là một quan hệ chia sẻ cần phân tích riêng.

### 13.3. Cùng tham chiếu không có nghĩa giá trị không đổi theo thời gian

Một đối tượng có thể giữ nguyên danh tính trong khi trường bên trong thay đổi.

Vì vậy, `a == b` là `true` tại một thời điểm không chứng minh đối tượng là bất biến, an toàn giữa nhiều luồng hoặc phù hợp làm khóa băm có thể sửa tùy ý.

Cần phân biệt ba trục:

1. Danh tính đối tượng.
2. Bình đẳng logic tại trạng thái đang xét.
3. Quan hệ chia sẻ và khả năng thay đổi trạng thái.

## 14. Comparator trả 0 không luôn có nghĩa equals trả true

Khi cấu trúc dùng thứ tự so sánh, còn có một quan hệ cần tách khỏi hai quan hệ chính.

Ví dụ, comparator chỉ so sánh sản phẩm theo giá có thể coi hai sản phẩm khác mã là cùng vị trí thứ tự khi chúng có giá bằng nhau.

Điều đó không tự làm `equals` của sản phẩm trả `true`.

Trong `TreeSet` hoặc `TreeMap`, kết quả so sánh ảnh hưởng nhận diện phần tử hoặc khóa. Muốn chúng tuân thủ nhất quán hợp đồng tổng quát của tập hoặc map, cần thiết kế thứ tự phù hợp với bình đẳng.

Không áp dụng kết luận từ `HashSet` sang một cây có comparator khác tiêu chí mà chưa xem xét quan hệ so sánh. Cũng không dùng `compare(...) == 0` làm phép thay thế mọi `equals` trong ứng dụng.

## 15. Chương trình Java hoàn chỉnh

Chương trình dưới đây so sánh danh tính với bình đẳng logic ở ba tầng: đối tượng thường, phần tử trong collection và chính cấu trúc chứa.

Lưu vào tệp `ReferenceAndValueEqualityDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;

public class ReferenceAndValueEqualityDemo {
    static final class PlainProduct {
        private final String code;

        PlainProduct(String code) {
            this.code = code;
        }
    }

    static final class Product {
        private final String code;
        private final String label;

        Product(String code, String label) {
            this.code = Objects.requireNonNull(code);
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product that)) {
                return false;
            }
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }

        @Override
        public String toString() {
            return code + ":" + label;
        }
    }

    public static void main(String[] args) {
        String text1 = new String("java");
        String text2 = new String("java");
        System.out.println("String same reference: " + (text1 == text2));
        System.out.println("String same value: " + text1.equals(text2));

        PlainProduct plain1 = new PlainProduct("P1");
        PlainProduct plain2 = new PlainProduct("P1");
        System.out.println("Default equals: " + plain1.equals(plain2));

        Product p1 = new Product("P1", "Pen");
        Product p2 = new Product("P1", "Blue pen");
        Product alias = p1;
        System.out.println("Alias same reference: " + (p1 == alias));
        System.out.println("Products same reference: " + (p1 == p2));
        System.out.println("Products same value: " + p1.equals(p2));
        System.out.println("Equal hash codes: "
                + (p1.hashCode() == p2.hashCode()));

        List<Product> products = new ArrayList<>(List.of(p1));
        System.out.println("List contains equal product: "
                + products.contains(p2));
        System.out.println("List removes equal product: "
                + products.remove(p2));

        Set<Product> distinct = new HashSet<>(List.of(p1, p2));
        System.out.println("HashSet size: " + distinct.size());

        Map<Product, Integer> normalMap = new HashMap<>();
        normalMap.put(p1, 10);
        normalMap.put(p2, 20);
        System.out.println("HashMap size: " + normalMap.size());
        System.out.println("HashMap value: " + normalMap.get(p1));

        Map<Product, Integer> identityMap = new IdentityHashMap<>();
        identityMap.put(p1, 10);
        identityMap.put(p2, 20);
        System.out.println("IdentityHashMap size: " + identityMap.size());

        List<String> left = new ArrayList<>(List.of("A", "B"));
        List<String> right = new LinkedList<>(List.of("A", "B"));
        System.out.println("Lists same reference: " + (left == right));
        System.out.println("Lists same value: " + left.equals(right));

        Set<String> set1 = new HashSet<>(List.of("A", "B"));
        Set<String> set2 = new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("Sets same value: " + set1.equals(set2));

        Queue<String> queue1 = new ArrayDeque<>(List.of("A", "B"));
        Queue<String> queue2 = new ArrayDeque<>(List.of("A", "B"));
        System.out.println("ArrayDeque equals: " + queue1.equals(queue2));

        int[] array1 = {1, 2};
        int[] array2 = {1, 2};
        System.out.println("Array equals: " + array1.equals(array2));
        System.out.println("Array content equality: "
                + Arrays.equals(array1, array2));

        Object[] nested1 = {new int[]{1, 2}};
        Object[] nested2 = {new int[]{1, 2}};
        System.out.println("Nested array shallow equality: "
                + Arrays.equals(nested1, nested2));
        System.out.println("Nested array deep equality: "
                + Arrays.deepEquals(nested1, nested2));

        System.out.println("Objects.equals with nulls: "
                + Objects.equals(null, null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ReferenceAndValueEqualityDemo.java
java ReferenceAndValueEqualityDemo
```

Kết quả chuẩn:

```text
String same reference: false
String same value: true
Default equals: false
Alias same reference: true
Products same reference: false
Products same value: true
Equal hash codes: true
List contains equal product: true
List removes equal product: true
HashSet size: 1
HashMap size: 1
HashMap value: 20
IdentityHashMap size: 2
Lists same reference: false
Lists same value: true
Sets same value: true
ArrayDeque equals: false
Array equals: false
Array content equality: true
Nested array shallow equality: false
Nested array deep equality: true
Objects.equals with nulls: true
```

### 15.1. Vì sao PlainProduct không bằng nhau?

Hai đối tượng có cùng trường `code`, nhưng lớp không override `equals`. Chúng tiếp tục dùng bình đẳng tham chiếu mặc định của `Object`.

Chương trình cố ý không dựa vào `toString` hoặc mã băm của các đối tượng này để suy luận kết quả.

### 15.2. Vì sao Product bằng nhau dù label khác?

Lớp `Product` chọn `code` làm tiêu chí bình đẳng và tính mã băm theo cùng trường đó. Nhãn chỉ là thuộc tính mô tả trong mô hình ví dụ.

`p1` và `p2` được tạo bởi hai lời gọi `new`, nên khác tham chiếu. `alias` nhận từ phép gán `p1`, nên cùng tham chiếu với `p1`.

### 15.3. Vì sao contains, remove, set và map phản ứng như vậy?

List có thể tìm và xóa đối tượng bằng giá trị qua `p2`.

Tập băm gộp hai giá trị bằng nhau thành một phần tử. Map thông thường quản lý một ánh xạ; giá trị sau lời ghi thứ hai là 20.

Map theo danh tính giữ hai khóa vì hai đối tượng khác instance.

### 15.4. Vì sao không in nội dung HashSet hoặc IdentityHashMap để làm output chuẩn?

Ví dụ quan sát kích thước và giá trị truy vấn, không phụ thuộc thứ tự duyệt không được bảo đảm của những cấu trúc này.

Chọn output ổn định giúp thực nghiệm chứng minh đúng quan hệ đang học, thay vì vô tình học một thứ tự chỉ xuất hiện trong một lần chạy.

### 15.5. Vì sao cùng phần tử nhưng ArrayDeque không bằng nhau?

Bình đẳng nội dung của `List` không phải quy tắc tự động cho mọi collection. `ArrayDeque` không cung cấp `equals` theo trình tự phần tử như list.

Đối với mảng, cần chọn `Arrays.equals` hoặc `Arrays.deepEquals` theo cấu trúc cần so sánh.

## 16. Cách chọn phép so sánh trong mã thực tế

| Câu hỏi | Cách tiếp cận |
| --- | --- |
| Hai biến có trỏ cùng instance không? | So sánh tham chiếu phù hợp bằng `==` |
| Hai chuỗi có cùng nội dung không? | `String.equals`, hoặc phép đối chiếu riêng theo yêu cầu |
| Hai giá trị có thể null có bằng nhau theo lớp không? | `Objects.equals` |
| Hai đối tượng miền có cùng tiêu chí giá trị không? | Thiết kế và dùng `equals` đúng hợp đồng |
| Hai list có cùng dãy phần tử không? | Hợp đồng `List.equals` |
| Hai set có cùng thành viên không? | Hợp đồng `Set.equals` với phần tử và cấu trúc nhất quán |
| Hai map thông thường có cùng ánh xạ không? | Hợp đồng `Map.equals` |
| Hai mảng một chiều có cùng nội dung không? | Overload `Arrays.equals` phù hợp |
| Hai mảng đối tượng có mảng lồng cần so nội dung không? | `Arrays.deepEquals` theo hợp đồng |
| Thuật toán cần phân biệt các instance cùng giá trị? | Cấu trúc theo danh tính phù hợp và được chọn có chủ ý |

Cần đọc đúng kiểu đang dùng: `Objects.equals` không tự áp dụng quy tắc list cho deque, và `Arrays.deepEquals` không tự hiểu mọi quan hệ nghiệp vụ trong lớp tự định nghĩa.

## 17. Lỗi thường gặp và cách chẩn đoán

### 17.1. equals luôn trả false với các đối tượng có cùng dữ liệu

Kiểm tra lớp có override đúng `equals(Object)` không, hay chỉ có overload với kiểu cụ thể. Dùng `@Override` và xem tiêu chí so sánh.

### 17.2. contains hoặc get không tìm thấy khóa được tạo lại

Kiểm tra đồng thời:

- `equals` có coi đối tượng truy vấn bằng đối tượng đã lưu không?
- `hashCode` có nhất quán với `equals` không?
- Trường dùng trong so sánh hoặc băm có bị đổi sau khi lưu không?
- Có đang dùng cấu trúc so sánh theo comparator hoặc danh tính không?

Không kết luận ngay rằng collection bị lỗi.

### 17.3. Set có ít phần tử hơn số lần thêm

Có thể các phần tử được coi là bằng nhau. Hãy kiểm tra dữ liệu đầu vào và tiêu chí bình đẳng.

Nếu thật sự cần giữ mọi lần xuất hiện, một list hoặc mô hình có đếm số lượng có thể phù hợp hơn. Không sửa `equals` để ép tập hợp chứa các giá trị mà nó đang phải coi là trùng.

### 17.4. Hai đối tượng in giống nhau nhưng không bằng nhau

`toString` là biểu diễn, không phải định nghĩa bắt buộc của bình đẳng. Cần xem hợp đồng lớp và phương thức thực sự được gọi.

### 17.5. Hai list chứa mảng cho kết quả ngoài dự đoán

Đi từ ngoài vào trong: list so sánh từng phần tử; phần tử mảng dùng bình đẳng nào? Có cần so sánh nội dung mảng tường minh không?

### 17.6. Dùng == trên wrapper vì cache

Một số giá trị dùng chung đối tượng nên phép so sánh tham chiếu cho `true`. Đó không phải cơ sở chọn toán tử cho bình đẳng giá trị tổng quát.

Vấn đề được sửa bằng chọn đúng quan hệ so sánh, không phải ghi nhớ thêm các khoảng số trong cache.

## 18. Bài tập tự kiểm chứng

### Bài 1: Vẽ đồ thị tham chiếu

Tạo một đối tượng, gán cho hai biến, rồi gán lại một biến sang đối tượng mới cùng dữ liệu.

Vẽ trước và sau. Dự đoán `==` và `equals` với lớp mặc định, rồi với lớp có bình đẳng theo mã.

### Bài 2: Thiết kế bình đẳng cho hai kiểu dữ liệu

Một kiểu đại diện điểm tọa độ, một kiểu đại diện khách hàng có mã ổn định và tên có thể đổi.

Hãy chọn thuộc tính tham gia bình đẳng cho từng kiểu, giải thích vì sao và viết `hashCode` nhất quán. Không mặc định một công thức giống nhau cho hai mô hình.

### Bài 3: Phần tử khác tham chiếu trong collection

Tạo hai đối tượng bằng giá trị nhưng khác tham chiếu. Dùng chúng với `ArrayList`, `HashSet`, `HashMap` và `IdentityHashMap`.

Dự đoán `contains`, số phần tử hoặc số ánh xạ trước khi chạy. Giải thích cấu trúc nào dùng quan hệ nào.

### Bài 4: So sánh ở nhiều tầng

Thử các cặp:

- Hai list `[A, B]` khác lớp triển khai.
- Hai list `[A, B]` và `[B, A]`.
- Hai set cùng phần tử nhưng khác thứ tự thêm.
- Hai mảng `int[]` riêng có cùng nội dung.
- Hai list chứa hai mảng riêng có cùng nội dung.

Không chỉ ghi kết quả; hãy chỉ rõ phương thức được dùng ở tầng cấu trúc và tầng phần tử.

### Bài 5: Kiểm tra hợp đồng equals

Với lớp tự viết, kiểm tra:

- Cùng đối tượng.
- Khác đối tượng nhưng cùng tiêu chí.
- Khác ít nhất một thuộc tính quyết định.
- `null`.
- Đối tượng thuộc kiểu không phù hợp.
- Đổi thứ tự so sánh.
- Ba đối tượng để kiểm tra bắc cầu.
- Hai đối tượng bằng nhau có cùng mã băm.

Không kiểm tra rằng hai đối tượng không bằng nhau phải có mã băm khác, vì đó không phải yêu cầu hợp đồng.

### Bài 6: Chia sẻ và bình đẳng

Tạo bản sao nông một list có phần tử thay đổi được. Quan sát:

- Hai list có cùng tham chiếu không?
- Chúng có bằng nhau theo list không?
- Các phần tử tương ứng có cùng tham chiếu không?
- Sửa một phần tử chung làm bên nào nhìn thấy thay đổi?

Bài tập này buộc tách bình đẳng nội dung khỏi quan hệ chia sẻ dữ liệu.

## 19. Các kết luận cần tránh

- “Dữ liệu in ra giống nhau thì == phải true.”
- “equals luôn so mọi trường.”
- “equals mặc định tự so giá trị các thuộc tính.”
- “Hai đối tượng bằng nhau thì chắc chắn cùng instance.”
- “Hai mã băm bằng nhau thì hai đối tượng bằng nhau.”
- “identityHashCode là địa chỉ hoặc mã duy nhất tuyệt đối.”
- “Mọi collection đều equals theo nội dung giống List.”
- “Record hoặc list tự biến mảng bên trong thành so sánh sâu.”
- “Objects.equals tự sửa một equals sai hợp đồng.”
- “Cùng tham chiếu chứng minh đối tượng không thể thay đổi.”

Cách làm đúng bắt đầu bằng việc nói rõ quan hệ cần kiểm tra: danh tính instance, bình đẳng theo mô hình, bình đẳng cấu trúc chứa hay quan hệ thứ tự. Khi các lớp nghĩa được tách rõ, hành vi tìm kiếm, loại trùng, băm và so sánh collection có thể được giải thích bằng hợp đồng thay vì bằng phỏng đoán.
