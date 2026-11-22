# addAll, containsAll, removeAll và retainAll

Khi làm việc với nhiều phần tử, ta thường cần gộp dữ liệu, kiểm tra một nhóm yêu cầu, loại bỏ các giá trị bị chặn hoặc chỉ giữ những giá trị được chấp nhận. Java cung cấp bốn phương thức thuộc hợp đồng chung của `Collection` cho các tình huống đó: `addAll`, `containsAll`, `removeAll` và `retainAll`.

Điểm quan trọng không nằm ở chữ “All”, mà ở ba câu hỏi: **collection nào là đối tượng nhận lời gọi, collection đối số đóng vai trò gì, và kết quả có làm thay đổi dữ liệu hay không?** Nếu chưa phân biệt được ba điều này, chương trình có thể chạy mà vẫn xóa sai dữ liệu hoặc kiểm tra sai yêu cầu.

Bài này dùng Java 17, tập trung vào hợp đồng và cách áp dụng bốn phương thức. Chương trình đầy đủ có tên tệp, lệnh chạy và kết quả ở phần minh họa. Các đoạn Java ngắn khác là đoạn trích minh họa, không phải chương trình độc lập.

## 1. Mô hình chung: đối tượng nhận và collection đối số

Xét lời gọi:

```java
a.removeAll(b);
```

- `a` là collection nhận lời gọi, cũng là nơi có thể bị thay đổi.
- `b` cung cấp tiêu chí phần tử cần loại.
- Phương thức không tạo một collection kết quả để trả về.
- Nếu lời gọi kết thúc bình thường, `boolean` trả về cho biết `a` có bị thay đổi hay không.

Với `containsAll`, vai trò khác đi: `a` được kiểm tra có chứa đầy đủ các giá trị xuất hiện trong `b` không; phương thức này không phải thao tác sửa cấu trúc collection.

Bảng định hướng:

| Lời gọi | Cách đọc | Vai trò của đối số | Có sửa đối tượng nhận? |
| --- | --- | --- | --- |
| `a.addAll(b)` | Thêm các phần tử của `b` vào `a` | Nguồn phần tử | Có thể |
| `a.containsAll(b)` | `a` có chứa mọi giá trị mà `b` yêu cầu không? | Nhóm cần kiểm tra | Không theo hợp đồng thao tác |
| `a.removeAll(b)` | Xóa khỏi `a` mọi phần tử thuộc `b` | Nhóm bị loại | Có thể |
| `a.retainAll(b)` | Chỉ giữ trong `a` các phần tử thuộc `b` | Nhóm được giữ | Có thể |

Đổi vị trí `a` và `b` thường đổi cả câu hỏi lẫn dữ liệu bị sửa. Chẳng hạn, “quyền đang có chứa các quyền bắt buộc” phải viết theo chiều `granted.containsAll(required)`.

Các phương thức này được khai báo trong [Collection của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). `List`, `Set`, `Queue` và các lớp liên quan nhận được hợp đồng đó qua hệ thống interface. `Map` không phải `Collection`; muốn thao tác trên khóa, giá trị hoặc entry của map phải xác định rõ view tương ứng.

## 2. Đọc chữ ký trước khi đọc ví dụ

Bốn chữ ký là:

```java
boolean addAll(Collection<? extends E> c);
boolean containsAll(Collection<?> c);
boolean removeAll(Collection<?> c);
boolean retainAll(Collection<?> c);
```

Khối trên chỉ liệt kê khai báo phương thức, không phải mã để đặt trực tiếp vào `main`.

### 2.1. Vì sao addAll có ? extends E?

`addAll` đưa các phần tử từ nguồn vào collection nhận. Vì vậy, nguồn phải cung cấp các phần tử phù hợp với kiểu `E`.

Đoạn minh họa:

```java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2, 3);

numbers.addAll(integers);
```

`Integer` là kiểu con của `Number`, nên các phần tử trên được chấp nhận. Điều này không có nghĩa `List<Integer>` là kiểu con của `List<Number>`; wildcard của riêng tham số phương thức cho phép nhận nguồn phù hợp.

### 2.2. Vì sao ba phương thức còn lại nhận Collection<?>?

Chúng kiểm tra quan hệ có chứa, hoặc lọc những phần tử đã có trong collection nhận. Chúng không cần chép các phần tử từ đối số vào nơi nhận.

Chẳng hạn, biểu thức sau có thể biên dịch:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));
boolean changed = numbers.removeAll(List.of("x"));
```

Với `ArrayList` trong ví dụ này, không có phần tử nào khớp, nên danh sách giữ nguyên và `changed` là `false`.

Tuy nhiên, không được tổng quát thành “truy vấn bằng kiểu không phù hợp luôn trả `false`”. Một số collection hạn chế kiểu phần tử hoặc cách so sánh và có thể ném ngoại lệ theo hợp đồng của chúng. Chữ ký cho phép biên dịch chưa chứng minh mọi collection đều chấp nhận mọi giá trị khi chạy.

## 3. addAll: thêm nhiều phần tử vào collection nhận

### 3.1. Thêm phần tử, không thêm nguyên collection như một phần tử

Đoạn minh họa:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = List.of("B", "C");

boolean changed = a.addAll(b);
```

Kết quả:

```text
a = [A, B, B, C]
b = [B, C]
changed = true
```

Ở đây `a` là `ArrayList`, nên hai phần tử của `b` được nối vào cuối theo thứ tự của nguồn. `b` không bị lấy mất phần tử.

Nếu muốn chứa cả một danh sách như một phần tử, cần kiểu lồng như `List<List<String>>` và dùng `add(b)`. Đó là mô hình dữ liệu khác.

### 3.2. List và Set xử lý phần tử lặp khác nhau

Với `List`, thêm lại giá trị đã có vẫn có thể làm danh sách thay đổi, vì danh sách cho phép nhiều lần xuất hiện.

Với tập hợp:

```java
Set<String> codes = new LinkedHashSet<>(List.of("A", "B"));
boolean first = codes.addAll(List.of("B", "C", "C"));
boolean second = codes.addAll(List.of("A", "B"));
```

Kết quả:

```text
codes = [A, B, C]
first = true
second = false
```

Lần đầu thêm được giá trị mới `"C"`; các lần xuất hiện còn lại không tạo phần tử trùng trong tập hợp. Lần thứ hai không có giá trị mới nên không làm thay đổi tập.

Không suy ra rằng mọi `Set` đều in theo thứ tự thêm. Ví dụ chọn `LinkedHashSet` để thứ tự quan sát là xác định. Một `HashSet` không đưa ra cùng bảo đảm thứ tự duyệt.

### 3.3. Boolean trả về diễn đạt sự thay đổi

`false` không có nghĩa thao tác thất bại. Nó có thể cho biết mọi phần tử từ nguồn đã có trong một tập hợp.

Nếu thao tác không được hỗ trợ, phần tử không hợp lệ hoặc không thể thêm do hạn chế khác, phương thức có thể ném ngoại lệ. Không dùng `false` làm nhánh xử lý chung cho mọi lỗi thêm dữ liệu.

Với một `ArrayList` có thể sửa và nguồn độc lập, không rỗng, lời gọi thêm các phần tử sẽ làm kích thước tăng. Với một tập hợp, nguồn không rỗng vẫn có thể không tạo thay đổi.

### 3.4. Thứ tự phụ thuộc kiểu collection

Hợp đồng `Collection` không biến mọi cấu trúc thành danh sách. `List.addAll` có quy tắc nối phần tử; một cấu trúc có sắp xếp hoặc có ưu tiên tiếp tục tổ chức dữ liệu theo quy tắc riêng.

Đừng dùng `addAll` rồi mặc nhiên suy ra thứ tự duyệt toàn bộ collection là thứ tự của nguồn. Cần đọc hợp đồng của interface và lớp đang dùng.

## 4. containsAll: kiểm tra sự hiện diện của mọi giá trị cần tìm

### 4.1. Đây là câu hỏi theo chiều

Đoạn minh họa:

```java
Set<String> granted = Set.of("READ", "WRITE");
Set<String> required = Set.of("READ");

boolean allowed = granted.containsAll(required);
```

`allowed` là `true`. Nếu đổi chiều, `required.containsAll(granted)` là `false` vì `required` không chứa `"WRITE"`.

Có thể dùng mô hình suy luận sau:

```text
với mỗi giá trị x trong collection đối số:
    nếu collection nhận không chứa x:
        trả về false
trả về true
```

Đây là mô hình để hiểu ý nghĩa, không phải cam kết mọi lớp đều chạy đúng một vòng lặp cụ thể.

### 4.2. Không kiểm tra số lần xuất hiện

Đoạn minh họa:

```java
List<String> available = List.of("A");
boolean result = available.containsAll(List.of("A", "A", "A"));
```

`result` là `true`: từng yêu cầu kiểm tra giá trị `"A"` đều thấy giá trị đó tồn tại.

Không có cơ chế “dùng hết một lần xuất hiện rồi lấy lần tiếp theo”. Vì vậy, không dùng `containsAll` để chứng minh kho có đủ ba đơn vị hàng chỉ vì giỏ yêu cầu chứa cùng một mã ba lần.

Khi số lượng là điều kiện, cần đếm theo giá trị, chẳng hạn biểu diễn bằng `Map<String, Integer>`, rồi so sánh số lượng cần với số lượng hiện có.

### 4.3. Không kiểm tra thứ tự, đoạn liên tiếp hoặc bình đẳng danh sách

Biểu thức:

```java
List.of("A", "B").containsAll(List.of("B", "A"))
```

trả `true`. Nó không yêu cầu các phần tử xuất hiện đúng thứ tự trong đối số.

Thậm chí hai danh sách có cùng kích thước và cùng chứa mọi giá trị của nhau vẫn chưa chắc có cùng số lần lặp:

```text
a = [A, A, B]
b = [A, B, B]
```

Cả hai phép `containsAll` theo hai chiều đều là `true`, nhưng hai danh sách không bằng nhau.

Chọn phép kiểm tra theo nhu cầu:

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Mọi giá trị bắt buộc đều xuất hiện | `containsAll` |
| Hai danh sách cùng phần tử ở từng vị trí | `List.equals` |
| Cùng giá trị và cùng số lần lặp, không xét thứ tự | So sánh bảng tần suất |
| Một nhóm là đoạn liên tiếp trong danh sách | Kiểm tra đoạn hoặc thuật toán tìm chuỗi con phù hợp |
| Có ít nhất một giá trị chung | Kiểm tra giao không rỗng, không dùng containsAll thay thế |

### 4.4. Collection đối số rỗng

Một collection chứa mọi phần tử của collection rỗng, vì không có giá trị nào cần kiểm tra. Do đó `a.containsAll(empty)` là `true` với đối số rỗng hợp lệ, kể cả khi `a` rỗng.

Trong kiểm tra nghiệp vụ, điều đó có thể đúng hoặc có thể làm lộ lỗi dữ liệu đầu vào. Nếu danh sách quyền bắt buộc không được phép rỗng theo quy trình, phải xác minh điều kiện đó riêng. `containsAll` không tự biết “không có yêu cầu” có phải là cấu hình hợp lệ của ứng dụng hay không.

## 5. removeAll: loại mọi lần xuất hiện của các giá trị được chỉ định

### 5.1. Xóa theo tư cách thành viên

Với dữ liệu:

```text
a = [A, B, A, C]
b = [A, X]
```

sau `a.removeAll(b)`, danh sách `a` còn `[B, C]`; kết quả là `true`.

Cả hai lần xuất hiện `"A"` đều bị xóa. `"X"` không có trong `a` nên không tạo thêm tác động. Đối số không cần chứa `"A"` hai lần để loại được cả hai phần tử của danh sách.

Mô hình suy luận:

```text
giữ lại mỗi phần tử x của a khi x không thuộc b
```

### 5.2. Khác remove một phần tử

Với một `ArrayList<String>` chứa `[A, B, A]`:

- `remove("A")` xóa một lần xuất hiện phù hợp.
- `removeAll(List.of("A"))` xóa mọi lần xuất hiện `"A"`.

`removeAll` không phải phép trừ có đếm số lượng. Nếu có ba đơn vị hàng và chỉ muốn trừ một đơn vị, cần thuật toán hoặc kiểu dữ liệu biểu diễn số lượng phù hợp.

### 5.3. Gọi lại có thể trả false

Sau khi đã loại hết `"A"`, gọi lại với cùng nhóm giá trị bị loại không còn thay đổi danh sách.

Điều này hữu ích khi chỉ cần biết có phát sinh thay đổi để cập nhật giao diện hoặc ghi nhận trạng thái. Tuy nhiên, không dùng nó như bằng chứng rằng một thao tác nghiệp vụ bên ngoài cũng đã xảy ra đúng một lần.

### 5.4. Ứng dụng

`removeAll` phù hợp với những yêu cầu như:

- Loại mã hàng thuộc danh sách ngừng kinh doanh.
- Loại nhãn bị chặn khỏi nhóm nhãn hiện có.
- Tính phần tử có trong nhóm thứ nhất nhưng không thuộc nhóm thứ hai.
- Lọc các giá trị đã được xử lý khi không cần giữ số lần lặp của việc xử lý.

Nếu muốn giữ nguyên dữ liệu ban đầu, phải tạo cấu trúc kết quả riêng trước khi gọi.

## 6. retainAll: lọc collection nhận theo nhóm được giữ

### 6.1. Chỉ giữ phần tử đang tồn tại

Với dữ liệu:

```text
a = [A, B, A, C]
b = [A, C, X]
```

sau `a.retainAll(b)`, `a` là `[A, A, C]`; kết quả là `true`.

Ba điểm cần quan sát:

1. `"B"` bị loại vì không thuộc nhóm được giữ.
2. Hai lần xuất hiện `"A"` vẫn còn vì danh sách cho phép lặp.
3. `"X"` không được thêm vào: đối số là tiêu chí giữ, không phải nguồn để bổ sung phần tử thiếu.

Mô hình suy luận:

```text
giữ lại mỗi phần tử x của a khi x thuộc b
```

### 6.2. Với List, đây không phải giao có đếm số lần

Nếu `a = [A, A, A]` và `b = [A]`, `retainAll` giữ cả ba phần tử `"A"` trong `a`.

Nếu bài toán yêu cầu giao của hai nhóm theo số lượng nhỏ hơn ở mỗi phía, kết quả cần một lần `"A"`; `retainAll` không thực hiện phép toán đó.

Với hai tập hợp có quan hệ bình đẳng nhất quán, `retainAll` diễn đạt phép giao theo cách quen thuộc. Với danh sách, nên đọc nó như **lọc theo sự hiện diện**, tránh bỏ qua phần tử lặp.

### 6.3. Giữ nguyên thứ tự của phần còn lại trong List

Lọc một danh sách không phải sắp xếp theo đối số. Nếu danh sách ban đầu là `[C, A, B, A]` và đối số là `[A, C]`, sau lọc còn `[C, A, A]`.

Nguồn tiêu chí không áp đặt lại thứ tự của danh sách nhận.

### 6.4. Đối số rỗng xóa hết phần tử hiện có

Với danh sách có thể sửa:

```java
List<String> selected = new ArrayList<>(List.of("A", "B"));
selected.retainAll(List.of());
```

danh sách `selected` trở thành rỗng.

Đây là hành vi đúng: không có giá trị nào nằm trong nhóm được giữ. Nếu ứng dụng coi danh sách được phép rỗng là “chưa tải được cấu hình”, gọi `retainAll` ngay có thể làm mất dữ liệu đang chọn. Phải phân biệt trạng thái tải lỗi với một tập cho phép rỗng hợp lệ.

## 7. So sánh đồng thời trên cùng dữ liệu ban đầu

Trong bảng dưới, mỗi dòng bắt đầu từ một bản `ArrayList` độc lập có nội dung `[A, B, A, C]`. Đối số là `[A, D]`.

| Phương thức | Giá trị trả về | Nội dung sau lời gọi | Cách hiểu |
| --- | --- | --- | --- |
| `addAll` | `true` | `[A, B, A, C, A, D]` | Bổ sung các phần tử từ nguồn |
| `containsAll` | `false` | `[A, B, A, C]` | Thiếu `D` |
| `removeAll` | `true` | `[B, C]` | Xóa mọi phần tử thuộc đối số |
| `retainAll` | `true` | `[A, A]` | Chỉ giữ phần tử thuộc đối số |

Không lấy kết quả của dòng trước làm đầu vào dòng sau rồi kỳ vọng còn khớp bảng này. Ba trong bốn phương thức có thể sửa đối tượng nhận.

## 8. Các trường hợp rỗng và giá trị boolean

Bảng dưới áp dụng cho `ArrayList` có thể sửa, các đầu vào độc lập và hợp lệ:

| Tình huống | Kết quả | Trạng thái nơi nhận |
| --- | --- | --- |
| `a.addAll(empty)` | `false` | Giữ nguyên |
| `a.containsAll(empty)` | `true` | Giữ nguyên |
| `empty.containsAll(nonEmpty)` | `false` | Giữ nguyên |
| `a.removeAll(empty)` | `false` | Giữ nguyên |
| `nonEmpty.retainAll(empty)` | `true` | Trở thành rỗng |
| `empty.retainAll(empty)` | `false` | Vẫn rỗng |
| `empty.addAll(nonEmpty)` | `true` | Chứa các phần tử nguồn |
| `empty.removeAll(nonEmpty)` | `false` | Vẫn rỗng |

Tách hai kiểu ý nghĩa của `boolean`:

- `containsAll`: câu trả lời cho điều kiện có chứa.
- `addAll`, `removeAll`, `retainAll`: có thay đổi collection nhận khi lời gọi kết thúc bình thường hay không.

Không gọi các phương thức này chỉ để kiểm tra “liệu có thay đổi không” nếu chưa muốn thay đổi dữ liệu. Riêng các phương thức sửa sẽ thực hiện thay đổi trước khi trả kết quả.

## 9. Dùng với phép toán tập hợp và giữ nguyên dữ liệu gốc

Khi hai đầu vào thực sự là các tập hợp, có thể tính:

```text
hợp:       bản sao của A rồi addAll(B)
giao:      bản sao của A rồi retainAll(B)
hiệu A−B:  bản sao của A rồi removeAll(B)
```

Đoạn minh họa:

```java
Set<String> union = new LinkedHashSet<>(a);
union.addAll(b);
```

Tên `union` được chọn vì biến này đại diện kết quả mới. Cách viết `Set<String> union = a;` chỉ tạo thêm một tham chiếu tới cùng tập hợp; gọi `addAll` sau đó vẫn sửa `a`.

Với danh sách, cần chọn rõ:

- Muốn giữ phần tử lặp: tạo `ArrayList` kết quả.
- Muốn loại phần tử lặp: tạo `Set` kết quả.
- Muốn giữ thứ tự xuất hiện khi loại lặp: chọn lớp triển khai có bảo đảm tương ứng, ví dụ `LinkedHashSet`.
- Muốn xử lý theo số lượng xuất hiện: dùng bảng đếm hoặc thuật toán đa tập phù hợp.

Sao chép collection theo các cách trên không tạo bản sao sâu của từng đối tượng bên trong. Nó giúp tách cấu trúc chứa phần tử, còn quyền sửa các đối tượng phần tử vẫn phải được xem xét riêng.

## 10. Bình đẳng, Comparator và đối tượng tự định nghĩa

Bốn phương thức không hiểu khái niệm “cùng người”, “cùng mã hàng” hay “cùng quyền” nếu mô hình dữ liệu không diễn đạt điều đó.

### 10.1. equals và hashCode

Với collection dùng bình đẳng theo giá trị, kết quả phụ thuộc cách lớp phần tử định nghĩa `equals`. Khi dùng cấu trúc băm, `hashCode` phải nhất quán với `equals`.

Nếu hai đối tượng có cùng mã nghiệp vụ nhưng vẫn dùng bình đẳng theo danh tính tham chiếu của `Object`, `containsAll` có thể không tìm được đối tượng mà người học tưởng là “giống nhau”.

Cần quyết định tiêu chí bình đẳng trước khi dùng collection làm công cụ đối chiếu dữ liệu.

### 10.2. Collection có thứ tự so sánh

Một `TreeSet` xác định sự tương đương qua phép so sánh. Nếu comparator không nhất quán với `equals`, các phép đối chiếu giữa collection có thể đem lại kết quả trái với trực giác của hợp đồng tập hợp.

Không pha trộn tùy tiện một tập so sánh không phân biệt hoa thường với một collection dùng `String.equals` rồi coi chúng đang dùng cùng một quan hệ bình đẳng. Có thể chuẩn hóa dữ liệu về khóa so sánh nhất quán trước khi thực hiện phép toán.

### 10.3. Không phụ thuộc số lần gọi equals

Để giải thích, có thể hình dung một vòng lặp kiểm tra thành viên. Nhưng không được thiết kế mã nghiệp vụ dựa vào giả định `equals` sẽ được gọi đúng một số lần hoặc theo một thứ tự cố định. Các lớp triển khai có quyền tối ưu theo cách phù hợp hợp đồng.

Các lớp nền [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) và [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html) minh họa những chiến lược triển khai khác nhau. Chúng hữu ích để hiểu cơ chế, nhưng không thay thế hợp đồng của lớp đang dùng thực tế.

## 11. Khả năng sửa, ngoại lệ và tác động một phần

### 11.1. Ba thao tác sửa là thao tác tùy chọn

`addAll`, `removeAll` và `retainAll` không được mọi collection hỗ trợ.

Ví dụ:

```java
List<String> fixed = List.of("A", "B");
fixed.removeAll(List.of("A"));
```

Lời gọi sửa danh sách trên ném `UnsupportedOperationException`. Muốn sửa, có thể tạo `new ArrayList<>(fixed)` rồi thao tác trên bản mới.

Một danh sách kích thước cố định từ `Arrays.asList` không phải danh sách cho phép thêm hoặc xóa. Việc nó hỗ trợ `set` không suy ra hỗ trợ các thao tác làm đổi kích thước.

### 11.2. Không dựa vào đầu vào rỗng để né ngoại lệ

Với thao tác không được hỗ trợ, hợp đồng collection cho phép một số lời gọi không có tác dụng vẫn ném `UnsupportedOperationException`. Không thiết kế mã dựa vào suy luận “không có gì cần xóa nên chắc chắn không lỗi”.

Bảng về đầu vào rỗng ở trên đã chỉ rõ dùng `ArrayList` có thể sửa. Nó không phải lời hứa cho mọi collection tùy ý.

### 11.3. null và kiểu phần tử không hợp lệ

Cần phân biệt:

1. Truyền `null` thay cho chính collection đối số.
2. Truyền collection hợp lệ nhưng có phần tử `null`.

Bốn phương thức không coi đối số collection `null` là collection rỗng; đó là lỗi có thể dẫn tới `NullPointerException` theo hợp đồng.

Với phần tử `null`, hành vi phụ thuộc khả năng của các collection tham gia. Trong `removeAll` và `retainAll`, phép kiểm tra thành viên có thể đi vào đối số; vì thế cả collection nhận lẫn collection tiêu chí đều cần được xem xét.

Cũng cần nhớ `List.of(null)` tự ném ngoại lệ ngay khi tạo danh sách. Lỗi đó xảy ra trước khi gọi phương thức hàng loạt, nên không dùng nó để kết luận phương thức đang kiểm thử xử lý `null` thế nào.

Một số trường hợp khác có thể gặp `ClassCastException`, `IllegalArgumentException` hoặc, khi thêm bị giới hạn sức chứa, `IllegalStateException`. Đọc phần ngoại lệ của đúng phương thức và đúng lớp.

### 11.4. Không có bảo đảm giao dịch toàn bộ hoặc không gì cả

Chữ “All” không mang nghĩa nguyên tử.

Nếu một lần thêm hoặc một phép kiểm tra thành viên gặp ngoại lệ giữa chừng, hợp đồng chung không bảo đảm mọi thay đổi trước đó sẽ được hoàn tác. Trạng thái sau lỗi phụ thuộc cách triển khai và nơi xảy ra lỗi.

Không viết quy trình:

```text
thử sửa dữ liệu gốc bằng thao tác hàng loạt
nếu có lỗi thì mặc nhiên coi dữ liệu gốc chưa đổi
```

Nếu cần bảo vệ cấu trúc gốc khỏi tác động một phần, có thể:

1. Tạo một cấu trúc làm việc riêng có kiểu và ngữ nghĩa phù hợp.
2. Áp dụng thao tác lên cấu trúc đó.
3. Chỉ công bố kết quả sau khi kiểm tra thành công.
4. Dùng cơ chế đồng bộ hoặc giao dịch phù hợp nếu việc công bố phải nguyên tử.

Cách làm này không tự sao chép sâu các phần tử và không hoàn tác tác dụng phụ bên ngoài của mã người dùng, chẳng hạn một `equals` tùy chỉnh có hành vi phụ.

## 12. Alias, view và sửa dữ liệu ngoài ý muốn

### 12.1. Hai biến cùng trỏ một collection

Đoạn minh họa:

```java
List<String> original = new ArrayList<>(List.of("A", "B"));
List<String> filtered = original;
filtered.retainAll(List.of("A"));
```

`original` cũng còn `[A]`, vì hai biến trỏ cùng đối tượng. Tên biến mới không tạo dữ liệu mới.

### 12.2. View gắn với cấu trúc nền

Các view như `Map.keySet()`, `Map.values()` hoặc `List.subList(...)` có thể chia sẻ dữ liệu với cấu trúc nền. Khi thao tác xóa được hỗ trợ, `removeAll` hoặc `retainAll` qua view có thể xóa dữ liệu tương ứng trong nguồn.

Ví dụ, lọc tập khóa của map bằng `retainAll` có thể xóa cả các ánh xạ có khóa bị loại. Đây có thể là mục tiêu mong muốn, nhưng cần diễn đạt rõ trong thiết kế.

Không suy ra view nào cũng cho thêm phần tử chỉ vì nó là `Collection`. Đặc biệt, thêm khóa mới qua một tập khóa thường không đủ thông tin về giá trị để tạo ánh xạ.

### 12.3. Không dùng addAll với chính collection không rỗng làm nguồn

Hợp đồng chung của `Collection.addAll` không xác định hành vi khi nguồn bị sửa trong lúc thao tác; nó nêu cả trường hợp nguồn chính là collection nhận và collection đó không rỗng.

Vì vậy, không viết `a.addAll(a)` như cách tổng quát để nhân đôi. Một lớp cụ thể có thể cho ra kết quả trông hợp lý, nhưng đó không phải bảo đảm có thể áp dụng cho mọi `Collection`.

Nếu cần lặp lại nội dung một danh sách, hãy tạo nguồn độc lập trước:

```java
List<String> extra = new ArrayList<>(a);
a.addAll(extra);
```

Tương tự, không để nguồn là view chồng lấn với nơi nhận mà chưa đọc hợp đồng. Tạo bản chụp phù hợp giúp tránh nhiều phụ thuộc alias, nhưng vẫn phải giải quyết truy cập đồng thời nếu dữ liệu có thể bị luồng khác sửa.

## 13. Chi phí xử lý và cách chọn collection tiêu chí

Không có một độ phức tạp chung cho tất cả lớp triển khai của bốn phương thức.

Gọi:

- `n` là kích thước collection nhận.
- `m` là kích thước collection đối số.

Nếu thuật toán duyệt qua một phía và gọi `contains` trên phía còn lại, chi phí phụ thuộc mạnh vào cấu trúc được dùng cho kiểm tra thành viên.

### 13.1. Trực giác với danh sách

Khi cả hai phía đều là danh sách và kiểm tra tồn tại phải dò tuyến tính:

- Kiểm tra mọi phần tử của đối số có thể cần đến khoảng `O(n × m)` phép làm việc.
- Lọc các phần tử của nơi nhận theo danh sách tiêu chí cũng có thể có chi phí cùng bậc.

Thời gian còn phụ thuộc dừng sớm, dữ liệu lặp và chi phí `equals`. Không diễn giải biểu thức độ phức tạp thành số mili giây cố định.

### 13.2. Chuẩn bị Set làm tiêu chí

Nếu quan hệ bình đẳng được giữ nguyên và thao tác thực sự cần kiểm tra thành viên nhiều lần, có thể chuyển tiêu chí thành `HashSet`:

```java
Set<String> allowed = new HashSet<>(allowedValues);
List<String> result = new ArrayList<>(source);
result.retainAll(allowed);
```

Với bảng băm có phân bố phù hợp, tra cứu thành viên có chi phí kỳ vọng gần hằng số. Kết hợp việc xây tập tiêu chí và duyệt nguồn có thể đưa mô hình chi phí về gần tuyến tính theo tổng kích thước trong những trường hợp phù hợp.

Điều kiện cần xem xét:

- Có thêm chi phí tạo tập và dùng bộ nhớ.
- Tập bỏ phần tử lặp; điều đó phù hợp với lọc theo thành viên, nhưng không phù hợp nếu nghiệp vụ cần đếm.
- Phải bảo đảm `equals`–`hashCode` đúng.
- Không đổi sang `HashSet` nếu việc đó làm thay đổi quan hệ so sánh mà bài toán đang dùng.
- Với dữ liệu nhỏ hoặc chỉ gọi một lần, chi phí chuẩn bị có thể không đáng.
- Lớp triển khai có thể có thuật toán riêng, nên cần kiểm tra tài liệu hoặc đo trên tải thực.

### 13.3. HashSet ở phía nhận chưa đủ để kết luận thao tác luôn nhanh

Một triển khai `removeAll` có thể chọn hướng duyệt dựa trên kích thước hai phía. Có hướng gọi `remove` trên tập nhận; có hướng duyệt tập rồi gọi `contains` trên đối số.

Do đó, chỉ nhìn kiểu của `a` trong `a.removeAll(b)` chưa đủ để khẳng định mọi công việc là `O(n + m)`. Hợp đồng triển khai `AbstractSet.removeAll` là ví dụ nên đọc để hiểu sự khác biệt.

Tài liệu [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) và [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) giúp xác định đặc điểm lớp, còn phép đo phải dùng dữ liệu cùng ngữ nghĩa kết quả.

## 14. Chương trình Java hoàn chỉnh

Chương trình sau dùng các bản sao độc lập để bốn nhóm kết quả không vô tình phụ thuộc thay đổi của nhau. Dữ liệu là chuỗi, nên không cần tự định nghĩa bình đẳng nghiệp vụ trong ví dụ.

Lưu vào tệp `BulkCollectionDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class BulkCollectionDemo {
    public static void main(String[] args) {
        List<String> source = List.of("A", "B", "A", "C");
        List<String> incoming = List.of("B", "D");

        List<String> appended = new ArrayList<>(source);
        boolean added = appended.addAll(incoming);
        System.out.println("addAll changed: " + added);
        System.out.println("appended: " + appended);

        System.out.println("contains A and D: "
                + appended.containsAll(List.of("A", "D")));
        System.out.println("contains repeated A: "
                + List.of("A").containsAll(List.of("A", "A", "A")));
        System.out.println("contains reversed order: "
                + List.of("A", "B").containsAll(List.of("B", "A")));

        List<String> removed = new ArrayList<>(source);
        boolean removedAny = removed.removeAll(List.of("A", "X"));
        System.out.println("removeAll changed: " + removedAny);
        System.out.println("removed: " + removed);
        System.out.println("removeAll again: "
                + removed.removeAll(List.of("A", "X")));

        List<String> retained = new ArrayList<>(source);
        boolean retainedChanged = retained.retainAll(List.of("A", "C", "X"));
        System.out.println("retainAll changed: " + retainedChanged);
        System.out.println("retained: " + retained);
        System.out.println("retainAll again: "
                + retained.retainAll(List.of("A", "C", "X")));

        Set<String> codes = new LinkedHashSet<>(List.of("A", "B"));
        System.out.println("set addAll changed: "
                + codes.addAll(List.of("B", "C", "C")));
        System.out.println("set: " + codes);
        System.out.println("set existing only: "
                + codes.addAll(List.of("A", "B")));

        Set<String> union = new LinkedHashSet<>(source);
        union.addAll(incoming);
        Set<String> intersection = new LinkedHashSet<>(source);
        intersection.retainAll(incoming);
        Set<String> difference = new LinkedHashSet<>(source);
        difference.removeAll(incoming);

        System.out.println("union: " + union);
        System.out.println("intersection: " + intersection);
        System.out.println("difference: " + difference);
        System.out.println("source unchanged: " + source);

        List<String> emptyCase = new ArrayList<>(List.of("A"));
        System.out.println("contains empty: " + emptyCase.containsAll(List.of()));
        System.out.println("retain empty changed: "
                + emptyCase.retainAll(List.of()));
        System.out.println("after retain empty: " + emptyCase);

        List<Number> numbers = new ArrayList<>();
        numbers.addAll(List.of(1, 2));
        System.out.println("numbers: " + numbers);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BulkCollectionDemo.java
java BulkCollectionDemo
```

Kết quả chuẩn:

```text
addAll changed: true
appended: [A, B, A, C, B, D]
contains A and D: true
contains repeated A: true
contains reversed order: true
removeAll changed: true
removed: [B, C]
removeAll again: false
retainAll changed: true
retained: [A, A, C]
retainAll again: false
set addAll changed: true
set: [A, B, C]
set existing only: false
union: [A, B, C, D]
intersection: [B]
difference: [A, C]
source unchanged: [A, B, A, C]
contains empty: true
retain empty changed: true
after retain empty: []
numbers: [1, 2]
```

Những dòng cần đối chiếu:

- `appended` vẫn có các phần tử `B` lặp, vì nơi nhận là danh sách.
- `contains repeated A` là `true` dù bên được kiểm tra chỉ có một phần tử `A`.
- `contains reversed order` là `true`, chứng minh phép kiểm tra không diễn đạt thứ tự.
- `removed` không còn bất kỳ lần xuất hiện `A` nào.
- `retained` vẫn giữ hai lần `A`.
- Các lần lọc lại không làm thay đổi dữ liệu nên trả `false`.
- `union`, `intersection`, `difference` là tập hợp mới, còn danh sách nguồn vẫn giữ nguyên.
- Các tập dùng `LinkedHashSet` để kết quả in ra theo thứ tự xác định.
- `numbers` chứng minh nguồn `Integer` có thể được thêm vào nơi nhận kiểu phần tử `Number`.

## 15. Khi nào cần cách xử lý khác?

### 15.1. Lọc theo điều kiện trên thuộc tính

Nếu muốn xóa mọi sản phẩm có giá nhỏ hơn một ngưỡng, đối số không phải một nhóm giá trị có sẵn. `removeIf` với điều kiện phù hợp thường diễn đạt rõ hơn `removeAll`.

Nếu chỉ muốn đối chiếu theo mã sản phẩm trong khi đối tượng có nhiều trường, cần xác định khóa đối chiếu và thuật toán lọc; đừng sửa `equals` tùy tiện chỉ để phục vụ một truy vấn.

### 15.2. Giữ nguyên nguồn và tạo kết quả

Có thể tạo một collection mới rồi gọi phương thức sửa trên bản đó. Stream cũng có thể diễn đạt lọc để tạo đầu ra riêng, nhưng phải chọn kết quả có thứ tự, phần tử lặp và khả năng sửa phù hợp.

`retainAll` tự nó không trả danh sách được lọc. Gán `List<String> result = a.retainAll(b)` là sai kiểu vì phương thức trả `boolean`.

### 15.3. Thay toàn bộ nội dung

Nếu mục đích là “đồng bộ nơi nhận thành dữ liệu của nguồn”, một mình `retainAll` không đủ vì không thêm giá trị còn thiếu; một mình `addAll` cũng không xóa giá trị thừa.

Cần thiết kế thao tác thay thế hoặc tính phần thêm, phần xóa theo yêu cầu. Nếu dữ liệu có thể bị đọc đồng thời, còn phải xác định ranh giới công bố kết quả, tránh để bên đọc thấy trạng thái trung gian.

### 15.4. Collection chia sẻ giữa nhiều luồng

Bốn lời gọi không tự tạo giao dịch trên hai collection.

Ngay cả khi một lớp hỗ trợ truy cập đồng thời, không được suy ra mọi thao tác hàng loạt hoặc chuỗi thao tác trên nhiều cấu trúc đều nguyên tử. Đối số cũng có thể thay đổi khi đang được duyệt.

Hãy đọc bảo đảm của đúng lớp và tổ chức đồng bộ, bản chụp hoặc mô hình sở hữu dữ liệu theo yêu cầu. Fail-fast iterator chỉ hỗ trợ phát hiện một số sửa đổi không hợp lệ; nó không thay thế kiểm soát đồng thời.

## 16. Bài tập tự kiểm chứng

### Bài 1: Dự đoán trước khi chạy

Cho `a = [red, blue, red, green]` và `b = [red, yellow]`. Với mỗi phương thức, tạo lại `a` từ dữ liệu ban đầu.

Hãy ghi trước:

- Giá trị `boolean`.
- Nội dung `a` sau lời gọi.
- Nội dung `b`.
- Có giữ phần tử lặp không?

Đáp án để đối chiếu:

| Phương thức | Boolean | a sau lời gọi |
| --- | --- | --- |
| `addAll` | `true` | `[red, blue, red, green, red, yellow]` |
| `containsAll` | `false` | `[red, blue, red, green]` |
| `removeAll` | `true` | `[blue, green]` |
| `retainAll` | `true` | `[red, red]` |

`b` giữ nguyên khi hai collection độc lập và không có hành vi phụ đặc biệt.

### Bài 2: Kiểm tra quyền bắt buộc

Có `granted = {READ, EXPORT}` và `required = {READ, WRITE}`.

Viết biểu thức kiểm tra đúng chiều. Kết quả phải là `false`. Sau đó tìm tập quyền còn thiếu bằng cách tạo bản sao của `required` rồi loại các quyền đã được cấp; tập còn lại chứa `WRITE`.

Câu hỏi bổ sung: nếu `required` rỗng, phép kiểm tra trả gì và chính sách nghiệp vụ của ứng dụng có chấp nhận điều đó không?

### Bài 3: Phân biệt số lượng với sự hiện diện

Cho kho hàng có một mã `A`, giỏ hàng yêu cầu ba lần mã `A`. Chứng minh `containsAll` không đủ bằng một ví dụ nhỏ, rồi viết lại kiểm tra theo bảng đếm.

Đừng sửa dữ liệu nguồn trong lúc chỉ đang xác minh đủ hàng.

### Bài 4: Bảo vệ dữ liệu gốc

Viết phương thức nhận danh sách nguồn và nhóm bị chặn, trả danh sách kết quả mới. Kiểm tra:

- Nguồn giữ nguyên.
- Mọi lần xuất hiện của mã bị chặn đều bị loại.
- Thứ tự của phần còn lại được giữ.
- Nhóm bị chặn rỗng.
- Nguồn rỗng.
- Không có phần tử khớp.

Sau đó giải thích vì sao đây chỉ là sao chép cấu trúc danh sách nếu phần tử là đối tượng có thể thay đổi.

### Bài 5: Lựa chọn cấu trúc tiêu chí

So sánh lọc một danh sách lớn với tiêu chí là danh sách và với tiêu chí là tập băm. Chỉ đo sau khi đã xác minh hai cách dùng cùng quan hệ bình đẳng và cho cùng kết quả.

Kết luận phải nêu cả chi phí chuẩn bị tập, bộ nhớ và số lần tái sử dụng tiêu chí.

## 17. Các điểm cần tự trả lời được

1. Trong `a.retainAll(b)`, bên nào bị sửa và bên nào chỉ làm tiêu chí?
2. Vì sao `containsAll` có thể trả `true` khi đối số chứa nhiều lần cùng một giá trị hơn nơi nhận?
3. `removeAll` khác gọi `remove` một lần thế nào?
4. Vì sao `retainAll` không bổ sung phần tử thiếu từ đối số?
5. `false` của `addAll` trên tập hợp có phải là lỗi không?
6. Đầu vào rỗng khác đầu vào `null` như thế nào?
7. Có thể dựa vào một lời gọi “không làm gì” để tránh `UnsupportedOperationException` trên mọi collection không?
8. Sau khi phương thức ném ngoại lệ, vì sao chưa được kết luận dữ liệu gốc còn nguyên?
9. Vì sao cần sao chép trước khi tính hiệu hoặc giao nếu nguồn phải được giữ lại?
10. View và hai biến tham chiếu cùng dữ liệu có thể làm thay đổi lan sang đâu?
11. Vì sao `HashSet` ở một phía chưa đủ để biết độ phức tạp toàn lời gọi?
12. Khi số lượng phần tử hoặc quan hệ so sánh khác nhau, cần thay đổi mô hình dữ liệu thế nào?

Điều cần nhớ khi áp dụng là: xác định bên nhận, hiểu đối số là nguồn hay tiêu chí, chọn đúng ngữ nghĩa phần tử lặp, rồi kiểm tra khả năng sửa và hiệu lực của kết quả. Các phương thức hàng loạt chỉ chính xác khi mô hình dữ liệu cùng hợp đồng mà chương trình dựa vào cũng chính xác.
