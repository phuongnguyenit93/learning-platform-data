# Khả năng tái sử dụng tập nguồn phù hợp khi dùng `Set.copyOf`

## 1. Vấn đề cốt lõi và mục tiêu

Từ **Java 10**, `Set.copyOf(Collection<? extends E>)` tạo ra một **`Set` không thể sửa đổi** từ các phần tử của một `Collection`. Một đặc điểm quan trọng của API này là **không nhất thiết cấp phát và sao chép một tập hợp mới trong mọi lần gọi**: khi collection đầu vào đã là một **unmodifiable Set** phù hợp, triển khai có thể **tái sử dụng chính tập nguồn**.

Điều này vừa là một cơ hội tối ưu hóa, vừa là một điểm dễ hiểu sai:

- **Hợp đồng phải tin cậy:** kết quả không cho sửa cấu trúc; các thay đổi sau này đối với collection nguồn không được phản ánh vào tập kết quả; kết quả không cho chứa `null`.
- **Chi tiết không được dựa vào:** JVM có cấp phát một `Set` mới không, `result == source` có đúng không, kiểu lớp triển khai cụ thể là gì, các phần tử được duyệt theo thứ tự nào.

Trong Java hiện đại, không nên viết logic nghiệp vụ dựa trên **danh tính đối tượng** của các collection sinh bởi `Set.of` và `Set.copyOf`. Câu hỏi đúng là: **dữ liệu và hành vi đã thỏa hợp đồng chưa?** chứ không phải **mỗi lần đã tạo được một đối tượng mới hay chưa?**

Sau bài học, bạn sẽ:

1. Giải thích được khi nào `Set.copyOf` *có thể* tái sử dụng một tập nguồn không sửa đổi phù hợp.
2. Phân biệt tập **unmodifiable do factory tạo** với **unmodifiable view** bọc một tập nguồn mutable.
3. Hiểu tại sao `Set.copyOf` từ nguồn mutable phải cho ra một **snapshot cấu trúc độc lập với thay đổi sau đó**.
4. Không suy luận kết quả từ `==`, `System.identityHashCode`, thứ tự duyệt hoặc tên lớp triển khai.
5. Xử lý `null`, phần tử trùng, mutable elements, generic, equality/hash và tình huống nhiều luồng.
6. Chạy ví dụ Java 17+ có stdout xác định được, không phụ thuộc chi tiết tối ưu hóa của một JDK cụ thể.

**Giới hạn kiến thức:** chỉ xem xét những quy tắc và API vẫn áp dụng trong Java hiện nay. `Set.of` (Java 9+) được dùng làm ví dụ đầu vào; `Set.copyOf` (Java 10+) là trọng tâm.

## 2. Hợp đồng `Set.copyOf` trong Java

Khai báo:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

Diễn giải:

| Phần | Ý nghĩa |
| --- | --- |
| `<E>` | Tham số kiểu generic của phần tử. |
| `Collection<? extends E>` | Nguồn có thể là `Set`, `List` hoặc collection phù hợp khác; **không bắt buộc** là một `Set`. |
| `coll` | Tham chiếu nguồn, phải **khác `null`**. |
| `Set<E>` kết quả | Một tập hợp không cho thêm, xóa hoặc cập nhật cấu trúc qua chính kết quả. |
| Dữ liệu | Chứa các phần tử của nguồn theo ngữ nghĩa tập hợp (không có phần tử trùng theo equality). |
| Sau khi nguồn thay đổi | Tập kết quả **không phản ánh** việc nguồn thêm, xóa phần tử hoặc thay cấu trúc sau khi tạo. |
| `null` | Nguồn `null` hoặc chứa phần tử `null` → `NullPointerException`. |
| Nguồn đã là unmodifiable `Set` | Theo *Implementation Note*, gọi `copyOf` **thường không cần** tạo bản sao. |

Tài liệu `Set.copyOf` cũng quy định: nếu collection nguồn có phần tử trùng, kết quả giữ **một phần tử đại diện bất kỳ** trong mỗi nhóm bằng nhau. Không hứa chọn phần tử nào khi các đối tượng khác nhau nhưng `equals` trả `true`.

Lưu ý tách hai lớp thông tin:

- **API contract:** tính không thể sửa đổi, nội dung tập kết quả, tính độc lập với thay đổi nguồn, NPE khi gặp `null`.
- **Implementation Note:** tối ưu hóa thường tránh sao chép nếu collection đầu vào đã là một `Set` không thể sửa đổi phù hợp.

Một *Implementation Note* **không biến việc tái sử dụng cùng instance thành bảo đảm mà ứng dụng được phép phụ thuộc**.

## 3. “Tái sử dụng tập nguồn” có nghĩa gì?

### 3.1. Tạo bản sao không sửa đổi từ nguồn đã ổn định

~~~java
import java.util.Set;

// Trong phương thức:
Set<String> source = Set.of("alpha", "beta");
Set<String> result = Set.copyOf(source);
~~~

`Set.of` trả về một `Set` không cho sửa đổi. Nếu runtime nhận biết rằng source đã thỏa các điều kiện cần thiết, nó **có thể** giữ lại chính instance `source` khi trả `result`. Không cần thiết tạo thêm một cấu trúc có cùng những phần tử `"alpha"`, `"beta"`.

Tuy nhiên, **đừng khẳng định**:

~~~java
// Không được dùng làm bất biến hay điều kiện bắt buộc:
boolean mustReuse = (source == result); // KHÔNG bảo đảm true
~~~

Điều đúng, ổn định, có thể kiểm thử:

~~~java
System.out.println(source.equals(result)); // true
System.out.println(result.size());          // 2
System.out.println(result.contains("alpha")); // true
~~~

Ở đây `equals` xác nhận **hai tập có cùng phần tử**. Nó không cần biết runtime cấp phát một instance hay tái sử dụng source.

### 3.2. Tập kết quả luôn không sửa được

~~~java
var source = Set.of("alpha", "beta");
var result = Set.copyOf(source);

// result.add("gamma"); // Khi chạy: UnsupportedOperationException
~~~

`Set<E>` có phương thức `add` nên lệnh gọi trên **có thể biên dịch**; nó ném `UnsupportedOperationException` khi chạy vì kết quả không cho sửa đổi.

Đối với `Set.of` và `Set.copyOf`, các phương thức thay đổi cấu trúc bị từ chối theo hợp đồng. Không nên dựa vào những trường hợp cập nhật “không tạo thay đổi” để suy luận ngoại lệ của các collection không sửa được khác, vì hợp đồng của từng implementation có thể khác.

### 3.3. Một tập rỗng cũng có thể được tái sử dụng

~~~java
var emptySource = Set.<String>of();
var emptyResult = Set.copyOf(emptySource);

System.out.println(emptyResult.isEmpty()); // true
~~~

Các runtime có thể tối ưu riêng những tập rỗng hoặc ít phần tử. Nhưng **không đoán cơ chế cache**, số lượng object tạo ra hay identity dựa trên kích thước 0, 1 hay 2. Hợp đồng chỉ yêu cầu kết quả phù hợp.

### 3.4. Kết quả `Set.copyOf` cũng là nguồn phù hợp cho lần gọi tiếp

~~~java
var first = Set.copyOf(Set.of("read", "write"));
var second = Set.copyOf(first);
var third = Set.copyOf(second);

System.out.println(first.equals(second)); // true
System.out.println(second.equals(third));  // true
~~~

Các lần gọi nối tiếp hợp lệ. Runtime được phép tránh tạo bản sao thừa vì những tập này đã là kết quả không sửa được phù hợp. **Không cần ép code phải tạo bản sao mới** bằng một collection mutable trung gian nếu mục tiêu chỉ là lấy một tập không sửa được.

Đây là trường hợp rất thực tế trong các tầng service, DTO hoặc constructor: mỗi tầng có thể gọi `Set.copyOf` như một thao tác **chuẩn hóa hợp đồng** mà không cần biết tầng trước đã chốt tập hay chưa.

## 4. Trường hợp đối lập: nguồn mutable bắt buộc phải có snapshot ổn định

Giả sử nguồn là `HashSet`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

// Trong phương thức:
var mutable = new HashSet<>(List.of("one", "two"));
Set<String> snapshot = Set.copyOf(mutable);

mutable.add("three");

System.out.println(mutable.contains("three"));  // true
System.out.println(snapshot.contains("three")); // false
~~~

Một bản `Set.copyOf(mutable)` hợp lệ phải **không bị thay đổi cấu trúc** chỉ vì `mutable` tiếp tục có thêm phần tử. Đây là lý do cần tạo snapshot độc lập với backing mutable set.

Nếu `Set.copyOf` chỉ trả về chính `mutable` thì ví dụ này sẽ làm sai hợp đồng: kết quả có thể sửa được và phản ánh `mutable.add("three")`. Vì vậy không thể dùng mục tiêu tối ưu hóa để hy sinh tính đúng đắn.

### 4.1. Hai câu hỏi khi quyết định có thể tái sử dụng hay không

**Câu hỏi 1:** Đối tượng nguồn đã từ chối cập nhật thông qua chính nó hay chưa?

**Câu hỏi 2:** Tập nguồn có **ổn định về membership** hay còn được cập nhật thông qua một tham chiếu/backing collection khác?

Một `Set` có vẻ “không cho sửa” qua một tham chiếu vẫn có thể **thay đổi gián tiếp** nếu nó là view bọc nguồn mutable. Do đó cần hiểu rõ **unmodifiable view** trước khi kết luận nguồn có thể tái sử dụng an toàn.

## 5. Unmodifiable `Set` do factory tạo và unmodifiable view khác nhau

### 5.1. `Set.of`: nguồn không sửa được, không có mutable backing set

~~~java
var fixed = Set.of("A", "B");
var result = Set.copyOf(fixed);
~~~

`fixed` không phải là view chỉ đọc của một `HashSet` đang được cập nhật bên ngoài. Nó là tập hợp do factory tạo và không cho sửa cấu trúc. Đây là ví dụ rõ ràng nhất về **nguồn phù hợp để runtime có thể tận dụng việc tái sử dụng**.

Không đồng nhất “tập không thể sửa cấu trúc” với “phần tử tuyệt đối bất biến”: nếu `fixed` chứa các đối tượng mutable, trạng thái các đối tượng ấy vẫn có thể thay đổi. Phần này được giải thích ở mục 9.

### 5.2. `Collections.unmodifiableSet`: view đọc xuyên qua nguồn

~~~java
var backing = new HashSet<>(List.of("A", "B"));
Set<String> view = Collections.unmodifiableSet(backing);

backing.add("C");
System.out.println(view.contains("C")); // true
~~~

`view` chặn `view.add(...)` nhưng **không cô lập nội dung** khỏi thay đổi thực hiện qua `backing`. Nó là **live view**, không phải snapshot.

Nếu cần chốt dữ liệu:

~~~java
var backing = new HashSet<>(List.of("A", "B"));
var liveView = Collections.unmodifiableSet(backing);
var snapshot = Set.copyOf(liveView);

backing.add("C");

System.out.println(liveView.contains("C")); // true
System.out.println(snapshot.contains("C")); // false
~~~

Vì `snapshot` không được phản ánh thay đổi cấu trúc của `liveView` sau khi copy, runtime phải đáp ứng ràng buộc đó. Trong trường hợp backing có thể thay đổi, **đừng suy luận từ chữ “unmodifiable” của view rằng `Set.copyOf` chắc chắn sẽ trả lại đúng reference `view`**.

Điểm chính xác cần nhớ:

- JavaDoc ghi rằng khi nguồn là unmodifiable `Set`, `copyOf` **thường** không tạo bản sao.
- Nhưng một wrapper view có thể **unmodifiable từ bên ngoài** đồng thời **không immutable về membership** vì nguồn được sửa bằng tham chiếu khác.
- Hợp đồng không phản ánh thay đổi nguồn có ưu tiên cao hơn bất kỳ suy đoán tối ưu hóa nào. **Code người dùng không được giả định reuse đối với view có backing mutable**.

### 5.3. So sánh ba loại nguồn

| Nguồn truyền vào `Set.copyOf` | Khả năng thay đổi về membership | Ý nghĩa thực tế |
| --- | --- | --- |
| `Set.of("A", "B")` | Không sửa cấu trúc qua nguồn | Runtime có thể tái sử dụng instance; không bảo đảm identity. |
| `Set.copyOf(...)` từ dữ liệu hợp lệ | Không sửa cấu trúc | Phù hợp để có thể reuse ở lời gọi tiếp theo. |
| `HashSet` hoặc `LinkedHashSet` mutable | Có thể thêm/xóa | Kết quả là snapshot không theo thay đổi sau này. |
| `Collections.unmodifiableSet(hashSet)` | View có thể thay đổi nếu `hashSet` bị sửa | Cần snapshot theo hợp đồng; không coi reuse là chắc chắn. |
| Set tùy chỉnh chỉ đọc | Phụ thuộc hợp đồng và cấu trúc backing thực tế | Không đoán identity; kiểm tra hành vi do API cam kết. |

Một **unmodifiable view** vẫn hữu ích nếu mục tiêu là cho người dùng chỉ đọc **dữ liệu hiện tại luôn cập nhật**. Nhưng nó không thay thế `Set.copyOf` khi bạn muốn chốt một trạng thái.

## 6. Dựa vào equality, không dựa vào reference identity

### 6.1. `equals` của `Set` nói gì?

Hai Set bằng nhau theo `equals` khi chúng có cùng số phần tử và chứa cùng các phần tử xét theo equality của Set, **không phụ thuộc thứ tự duyệt**.

~~~java
Set<String> left = Set.of("north", "south");
Set<String> right = Set.copyOf(left);

System.out.println(left.equals(right));  // true
System.out.println(right.equals(left));  // true
~~~

Đó là điều ứng dụng có thể trông đợi. Nó thể hiện dữ liệu và không lệ thuộc runtime.

### 6.2. `==` chỉ cho biết cùng instance, nhưng không được dùng làm hợp đồng

~~~java
// Một thử nghiệm kỹ thuật có thể quan sát, không phải bảo đảm:
boolean sameReference = (left == right);
~~~

`sameReference` có thể đúng hoặc sai tùy implementation, phiên bản JDK và cách nguồn được tạo. Không nên viết kiểm thử như:

~~~java
// SAI VỀ KỲ VỌNG: assert source == Set.copyOf(source);
// SAI VỀ KỲ VỌNG: assert source != Set.copyOf(source);
~~~

Cả **“luôn cùng object”** và **“luôn object mới”** đều là giả định không được JavaDoc cam kết.

### 6.3. Value-based instance và những điều cần tránh

Những tập hợp do `Set.of`/`Set.copyOf` tạo ra được mô tả là **value-based**. Do đó:

- Không dùng `==`/`!=` để quyết định nghiệp vụ hoặc số lần copy.
- Không dùng `System.identityHashCode(result)` làm mã định danh bền vững.
- Không lấy chính instance Set factory làm **monitor lock** với `synchronized(result)` để điều phối luồng.
- Không xây cache dựa trên giả định rằng mọi `Set.copyOf` với cùng nội dung đều trả về cùng một instance.

Dùng `equals`/`hashCode` theo nghĩa giá trị; nếu cần khóa đồng bộ, tạo một object chuyên làm lock, độc lập với collection value-based.

~~~java
private final Object lock = new Object();

// Đặt trong một class phù hợp:
void doWork() {
    synchronized (lock) {
        // thao tác cần bảo vệ
    }
}
~~~

Khối minh họa trên không phải phép đồng bộ cần thiết để *đọc* một tập dữ liệu bất biến; nó minh họa cách tránh lấy collection value-based làm khóa.

## 7. Tối ưu hóa bộ nhớ có thể có nhưng không phải một chỉ tiêu cam kết

Một động cơ của `copyOf` là dễ dàng tạo một **giá trị collection không sửa được** tại ranh giới API. Với nguồn đã đáp ứng hợp đồng, một implementation có thể:

- Trả về ngay instance đã có mà không copy phần tử.
- Sử dụng cấu trúc lưu trữ được tối ưu cho `Set` không sửa được.
- Tái sử dụng biểu diễn nội bộ cho tập rỗng/ít phần tử.
- Chọn tạo một đối tượng mới nếu implementation cần hoặc thấy phù hợp.

Nhưng JavaDoc **không cam kết** các yếu tố sau:

1. Cấp phát bằng 0 trong mọi trường hợp nguồn unmodifiable.
2. Độ phức tạp thời gian luôn là O(1).
3. Mức tiêu thụ bộ nhớ cụ thể.
4. Lớp runtime cụ thể, ví dụ tên các lớp nội bộ của JDK.
5. Số lần duyệt phần tử hoặc cách triển khai hash.
6. Tập nguồn và tập trả về luôn là cùng reference.

**Hướng tối ưu hóa đúng:** dùng `Set.copyOf` ở ranh giới dữ liệu theo hợp đồng; nếu hiệu năng thực sự quan trọng, đo bằng benchmark phù hợp với workload, phiên bản JDK và kích thước dữ liệu thay vì dựa vào `==` hoặc đoán Java sẽ copy mấy lần.

### 7.1. Không tự “tối ưu” bằng cách bỏ snapshot khi nguồn mutable

~~~java
static Set<String> publish(Set<String> incoming) {
    return Set.copyOf(incoming);
}
~~~

Đoạn này thích hợp khi `publish` cần trả về tập không sửa được và tách khỏi các thay đổi sau đó của `incoming`. Không thay bằng `return incoming;` chỉ để “tiết kiệm copy”, vì sẽ làm lộ nguồn mutable.

Với caller truyền `Set.of(...)`, implementation **có cơ hội tránh copy**. Với caller truyền `HashSet`, tính đúng đắn đòi snapshot. Bởi vậy `copyOf` rất hữu ích để **chuẩn hóa hợp đồng ngay tại một điểm**.

## 8. Những điều kiện làm nguồn không phù hợp để reuse một cách tùy tiện

### 8.1. Có `null`

~~~java
var nullable = new HashSet<String>();
nullable.add(null);

// Set.copyOf(nullable); // NullPointerException tại runtime
// Set.copyOf(null);     // NullPointerException tại runtime
~~~

`Set.copyOf` không tự xóa `null`, không đổi thành tập rỗng và không trả lại nguồn vi phạm hợp đồng. Nó **từ chối** nguồn hoặc phần tử `null`.

Nguồn `HashSet` có thể chứa `null` nhưng tập do `Set.copyOf` tạo không được chứa; đây là khác biệt hợp đồng cần xử lý ở ranh giới dữ liệu.

### 8.2. Source là `Collection` chứ không phải Set

~~~java
var input = List.of("x", "x", "y");
var result = Set.copyOf(input);

System.out.println(result.size());         // 2
System.out.println(result.contains("x"));  // true
System.out.println(result.contains("y"));  // true
~~~

`List` có thể chứa phần tử trùng, còn `Set` không. Vì thế `Set.copyOf(List.of("x", "x", "y"))` tạo kết quả với hai phần tử phân biệt. Không thể đơn giản trả về cùng reference `input` vì nó không phải `Set` và chứa duplicate.

Nếu hai đối tượng khác nhau nhưng `equals` bằng nhau, implementation có thể giữ **một đại diện bất kỳ**. Nếu nghiệp vụ yêu cầu “ưu tiên bản mới nhất” hoặc “ưu tiên trạng thái active”, phải tự chọn quy tắc trước khi chuyển thành Set.

### 8.3. Dùng `Set.of` với phần tử trùng là quy tắc khác

~~~java
// Set.of("x", "x"); // ném IllegalArgumentException
~~~

Khác biệt:

- `Set.of("x", "x")`: ném `IllegalArgumentException` do đối số trùng.
- `Set.copyOf(List.of("x", "x"))`: thành công, kết quả có một `"x"`.

Không coi `Set.copyOf` là bản sao cú pháp của `Set.of`; chúng có các chính sách khác nhau đối với đầu vào có duplicate.

### 8.4. Tập tùy chỉnh bị thay đổi bằng con đường khác

Một implementation `Set` tùy chỉnh có thể từ chối `add` nhưng đọc dữ liệu từ trạng thái bên ngoài thay đổi được. Lời gọi `Set.copyOf` không cấp phép giả định rằng tập này là *deep immutable* hay rằng có thể trả về chính instance của nó. Mục tiêu tối ưu hóa phải tuân theo **hành vi quan sát được** do API cam kết.

## 9. `Set.copyOf` là shallow copy, không làm bất biến các phần tử

Cho dù runtime copy cấu trúc hay tái sử dụng instance tập nguồn, các phần tử có thể vẫn là **cùng đối tượng**:

~~~java
class Label {
    private String name;

    Label(String name) {
        this.name = name;
    }

    void rename(String next) {
        name = next;
    }

    String name() {
        return name;
    }
}
~~~

Trong phương thức:

~~~java
var label = new Label("draft");
var source = Set.of(label);
var snapshot = Set.copyOf(source);

label.rename("edited");
System.out.println(snapshot.iterator().next().name()); // edited
~~~

Ở ví dụ này `Label` không tự ghi đè `equals`/`hashCode` nên việc đổi `name` không thay đổi identity-based equality của đối tượng. Dù vậy, trạng thái **phần tử** quan sát được đã đổi. Điều này chứng minh **unmodifiable Set không đồng nghĩa immutable element**.

### 9.1. Tuyệt đối cẩn trọng với key hash/equality mutable

Nếu phần tử `Set` thay đổi trạng thái được dùng trong `equals` hoặc `hashCode` trong lúc đang thuộc tập, hành vi của Set có thể trở nên **không xác định theo hợp đồng**. Một lệnh `contains` thậm chí có thể không tìm thấy phần tử mà ta vẫn thấy khi duyệt.

Hạn chế này vẫn tồn tại dù tập là `HashSet`, `Set.of` hay `Set.copyOf`. Việc reuse hay copy **không sửa được lỗi thiết kế của phần tử**.

Khuyến nghị: dùng các giá trị bất biến như `String`, `UUID`, các record bất biến hoặc những lớp có equality/hash ổn định làm phần tử Set. Khi cần chốt danh sách các đối tượng mutable, hãy chuyển từng phần tử thành một **giá trị bất biến phù hợp** trước khi tạo Set.

### 9.2. Ví dụ kiểu giá trị bất biến

~~~java
record Role(String code) {
    Role {
        java.util.Objects.requireNonNull(code);
    }
}

// Trong một phương thức:
var roles = Set.copyOf(List.of(new Role("READ"), new Role("WRITE")));
~~~

Với `Role` chỉ chứa một `String` bất biến, Set có các phần tử có trạng thái bình thường ổn định. Nếu record chứa tham chiếu tới `List` mutable thì vẫn phải defensive-copy trong constructor; `record` không tự deep-freeze mọi thành phần.

## 10. Thứ tự duyệt không phải một phần của kết quả được cam kết

Dù nguồn là `LinkedHashSet` có thứ tự chèn, `Set.copyOf` trả về một **Set không cam kết thứ tự duyệt**. Runtime có thể dùng biểu diễn khác hoặc tái sử dụng nguồn phù hợp theo lựa chọn của nó.

~~~java
var orderedSource = new java.util.LinkedHashSet<String>();
orderedSource.add("first");
orderedSource.add("second");

var result = Set.copyOf(orderedSource);

// Không dùng thứ tự in result.toString() làm kiểm thử bất biến.
System.out.println(result.contains("first"));  // true
System.out.println(result.contains("second")); // true
~~~

Nếu thứ tự là một yêu cầu nghiệp vụ, hãy tách hai nhu cầu:

- **Tập membership không sửa đổi:** `Set.copyOf` phù hợp.
- **Duy trì một thứ tự cụ thể:** dùng cấu trúc có hợp đồng thứ tự được thiết kế cho mục đích đó hoặc tạo một danh sách kết quả đã sắp xếp.

Không nên thêm test giả định `Set.copyOf` luôn duyệt theo thứ tự `LinkedHashSet` chỉ vì một lần chạy thấy thế.

## 11. Concurrency: không nên diễn dịch reuse là snapshot nguyên tử

Một `Set` trả về từ `Set.copyOf` không thể được thay đổi cấu trúc qua API của chính nó, nhưng **quá trình sao chép từ một nguồn đang bị sửa đồng thời** không mặc nhiên được đồng bộ hóa.

Tình huống nguy hiểm:

~~~java
var shared = new HashSet<String>();
// Thread 1: Set.copyOf(shared);
// Thread 2: shared.add("new");
~~~

Nếu không có giao thức bảo vệ nguồn, lúc đang duyệt/sao chép, dữ liệu có thể thay đổi không kiểm soát. `Set.copyOf` **không phải giao dịch snapshot nguyên tử** từ một `HashSet` đang có concurrent modifications.

Giải pháp tùy ứng dụng:

1. Đọc/sao chép dưới cùng cơ chế khóa đang bảo vệ nguồn.
2. Truyền một snapshot đã được tạo an toàn từ thành phần sở hữu dữ liệu.
3. Sử dụng collection đồng thời hoặc thiết kế dữ liệu copy-on-write phù hợp, nhưng vẫn phải hiểu semantic snapshot của chính cấu trúc đó.
4. Bảo đảm việc công bố (*safe publication*) của dữ liệu sang luồng khác; không coi một factory method tự giải quyết mọi vấn đề memory visibility.

Nếu source thật sự là tập không sửa cấu trúc và phần tử bất biến đã được công bố an toàn, việc runtime reuse hay tạo bản sao mới không làm thay đổi yêu cầu nghiệp vụ: dữ liệu quan sát được ổn định.

## 12. Cách chọn API trong dự án

| Bài toán | API phù hợp | Vì sao |
| --- | --- | --- |
| Biết sẵn vài phần tử tại chỗ | `Set.of("A", "B")` | Tạo Set không sửa được trực tiếp; không có mutable backing collection. |
| Nhận collection không chắc có sửa được không, muốn chuẩn hóa đầu ra | `Set.copyOf(input)` | Đảm bảo Set không sửa cấu trúc và snapshot theo hợp đồng; có cơ hội reuse nguồn phù hợp. |
| Đã có `Set.copyOf` từ tầng trước, cần đảm bảo contract tại tầng sau | `Set.copyOf(previous)` | Hợp lệ, có khả năng tránh copy thừa; không phải check identity. |
| Muốn người đọc thấy cập nhật mới nhất của nguồn nội bộ nhưng không cho sửa qua view | `Collections.unmodifiableSet(backing)` | Tạo live view; **không phải snapshot**. |
| Muốn tiếp tục thêm/xóa phần tử | `HashSet` hoặc collection mutable phù hợp | `copyOf` không dùng để sửa dữ liệu. |
| Nguồn có phần tử trùng và cần kết quả Set | `Set.copyOf(collection)` | Khử trùng theo equality; đại diện được giữ có thể bất kỳ. |
| Muốn thứ tự có ý nghĩa | List/SequencedSet hoặc một cấu trúc có hợp đồng thứ tự thích hợp | `Set.copyOf` không hứa thứ tự duyệt. |
| Dữ liệu phần tử mutable | Chuyển thành giá trị bất biến trước, rồi `Set.copyOf` | Copy cấu trúc không tạo deep immutability. |

### 12.1. Pattern cho constructor hoặc API trả dữ liệu

~~~java
import java.util.Collection;
import java.util.Set;

public final class Permissions {
    private final Set<String> codes;

    public Permissions(Collection<String> incoming) {
        this.codes = Set.copyOf(incoming);
    }

    public Set<String> codes() {
        return codes;
    }
}
~~~

Trong ví dụ này:

- Constructor bảo vệ tập kết quả khỏi thay đổi cấu trúc do caller tiếp tục sửa `incoming`.
- Nếu caller truyền `Set.of(...)` hoặc một unmodifiable Set tương đương, implementation có thể tránh sao chép thừa.
- Getter trả đúng tập không cho sửa đổi đã lưu, không phơi bày collection mutable nội bộ.
- Chính sách `null` được `Set.copyOf` thực thi: dữ liệu thiếu không được lặng lẽ chuyển thành một giá trị khác.

Nếu permission code có thứ tự nghiệp vụ hoặc cần lưu duplicate, dùng Set là sai mô hình dữ liệu, không phải lỗi của `copyOf`.

## 13. Chương trình Java 17+ đầy đủ và stdout ổn định

Tạo tệp **`SetCopyReuseDemo.java`**. Chương trình **không** in `source == result` vì đó không phải kết quả được JDK cam kết. Thay vào đó, nó kiểm thử các thuộc tính quan sát được.

~~~java
import java.util.*;

public class SetCopyReuseDemo {
    static final class Label {
        private String text;

        Label(String text) {
            this.text = text;
        }

        void rename(String next) {
            text = next;
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        var frozen = Set.of("alpha", "beta");
        var copiedFrozen = Set.copyOf(frozen);

        System.out.println("equal contents=" + frozen.equals(copiedFrozen));
        System.out.println("two values=" + (copiedFrozen.size() == 2));

        try {
            copiedFrozen.add("gamma");
        } catch (UnsupportedOperationException ex) {
            System.out.println("update blocked");
        }

        var mutable = new HashSet<>(List.of("one", "two"));
        var liveView = Collections.unmodifiableSet(mutable);
        var snap = Set.copyOf(mutable);
        var copiedView = Set.copyOf(liveView);

        mutable.add("three");

        System.out.println("live view updated=" + liveView.contains("three"));
        System.out.println("snapshot stable=" + !snap.contains("three"));
        System.out.println("copied view stable=" + !copiedView.contains("three"));

        var fromList = Set.copyOf(List.of("x", "x", "y"));
        System.out.println("deduplicated size=" + fromList.size());

        try {
            Set.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException ex) {
            System.out.println("null rejected");
        }

        var label = new Label("draft");
        var elements = Set.copyOf(Set.of(label));
        label.rename("edited");

        System.out.println(
                "shared element=" + elements.iterator().next().text());
    }
}
~~~

Lệnh biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 SetCopyReuseDemo.java
java SetCopyReuseDemo
~~~

**Stdout chính xác:**

~~~text
equal contents=true
two values=true
update blocked
live view updated=true
snapshot stable=true
copied view stable=true
deduplicated size=2
null rejected
shared element=edited
~~~

### 13.1. Vì sao các dòng này có ý nghĩa?

- **`equal contents=true`:** `Set.copyOf(Set.of(...))` chứa cùng phần tử; không kết luận identity.
- **`two values=true`:** kết quả có đúng hai phần tử phân biệt; không cần dựa vào thứ tự duyệt.
- **`update blocked`:** cố `add` lên kết quả không sửa được gây `UnsupportedOperationException`.
- **`live view updated=true`:** `Collections.unmodifiableSet(mutable)` đọc trạng thái nguồn mới nhất.
- **`snapshot stable=true`:** kết quả `Set.copyOf(mutable)` không nhận phần tử thêm sau lúc copy.
- **`copied view stable=true`:** `Set.copyOf(liveView)` cũng là snapshot, không phụ thuộc cách wrapper view được cập nhật về sau.
- **`deduplicated size=2`:** nguồn là List có `"x"` lặp lại; kết quả là Set gồm hai phần tử phân biệt.
- **`null rejected`:** đầu vào chứa `null` bị từ chối bằng `NullPointerException`.
- **`shared element=edited`:** kết quả giữ cùng đối tượng phần tử `Label`; copy cấu trúc không làm bất biến đối tượng.

Ví dụ này dùng các API vẫn được hỗ trợ trên Java 17+. Kết quả không phụ thuộc randomized iteration order của Set, số lần cấp phát, lớp triển khai trong JDK hoặc việc runtime tái sử dụng source.

## 14. Những kiểm thử nào là tốt và không tốt?

### 14.1. Kiểm thử tốt: hợp đồng quan sát được

~~~java
var source = Set.of("A", "B");
var snapshot = Set.copyOf(source);

assert snapshot.equals(source);
assert snapshot.size() == 2;
assert snapshot.contains("A");
assert snapshot.contains("B");
~~~

Với `assert`, có thể bật kiểm thử bằng tùy chọn JVM `-ea`, ví dụ `java -ea YourClass`. Những điều kiện này phản ánh hợp đồng dữ liệu.

Với một nguồn mutable:

~~~java
var mutable = new HashSet<>(Set.of("A", "B"));
var snapshot = Set.copyOf(mutable);
mutable.add("C");

assert !snapshot.contains("C");
~~~

Điều kiện này kiểm tra sự cô lập của snapshot khỏi thay đổi sau đó.

### 14.2. Kiểm thử không tốt: chi tiết triển khai

~~~java
var source = Set.of("A", "B");
var snapshot = Set.copyOf(source);

// KHÔNG nên:
// assert snapshot == source;
// assert snapshot != source;
// assert snapshot.getClass().getName().contains("ImmutableCollections");
~~~

Một phiên bản JDK có thể reuse và phiên bản khác tạo object mới. Cả hai vẫn có thể tuân thủ API. Việc unit test ép buộc tên lớp nội bộ, reference equality hoặc thứ tự duyệt sẽ tạo test mong manh.

Nếu thực sự cần đánh giá hiệu năng, hãy dùng benchmark chuyên biệt và đo các metrics có nghĩa, không biến giả định “Set.copyOf phải O(1)” thành yêu cầu chức năng.

## 15. Lỗi phổ biến cần tránh

| Ngộ nhận | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “`Set.copyOf` luôn cấp phát tập mới.” | Đoán sai hiệu năng, viết copy không cần thiết. | Runtime có thể reuse unmodifiable Set phù hợp. |
| “`Set.copyOf` luôn trả cùng reference nếu source đã unmodifiable.” | Test phụ thuộc JDK, dễ lỗi khi nâng cấp. | Reuse chỉ là khả năng tối ưu hóa, **không cam kết identity**. |
| “Bọc `HashSet` bằng `Collections.unmodifiableSet` là đã có snapshot.” | View đổi khi backing Set đổi. | Muốn chốt dữ liệu, dùng `Set.copyOf`. |
| “`Set.copyOf(view)` có thể phản ánh các thay đổi nguồn về sau.” | Vi phạm hợp đồng snapshot. | Kết quả `copyOf` không phản ánh thay đổi sau đó. |
| “Nếu copyOf reuse thì phần tử cũng bất biến.” | Object phần tử vẫn có thể đổi trạng thái. | `copyOf` là shallow, không deep-copy. |
| “Đổi trường dùng cho `hashCode` của phần tử Set không sao.” | Tra cứu/so sánh của Set có thể không còn đúng. | Giữ equality/hash của phần tử ổn định. |
| “`Set.copyOf` duyệt theo thứ tự `LinkedHashSet`.” | Logic và test phụ thuộc thứ tự không cam kết. | Dùng cấu trúc khác nếu thứ tự là hợp đồng. |
| “`Set.copyOf(List.of("A", "A"))` ném giống `Set.of`.” | Chẩn đoán sai exception. | `copyOf` gộp duplicate, `of` từ chối duplicate. |
| “Nguồn null sẽ thành tập rỗng.” | Gây `NullPointerException`. | Phải xử lý nguồn/element null trước khi gọi. |
| “Kết quả unmodifiable mặc nhiên thread-safe trong mọi trường hợp.” | Dữ liệu nguồn hoặc phần tử mutable vẫn có rủi ro cạnh tranh. | Quản lý concurrency và safe publication theo thiết kế. |
| “Dùng identity hash của tập kết quả làm khóa.” | Vi phạm hướng dẫn cho value-based instances. | Dựa vào nội dung và dùng lock riêng khi cần. |

## 16. Bài tập và đáp án

**Bài 1.** Với đoạn sau:

~~~java
var original = Set.of("A", "B");
var copy = Set.copyOf(original);
~~~

Có thể khẳng định `original == copy` không?

**Đáp án:** Không. `Set.copyOf` có thể tái sử dụng tập nguồn đã không sửa được, nhưng không hứa reference equality. Khẳng định được `original.equals(copy)` và kết quả không sửa được.

**Bài 2.** Một caller truyền `HashSet<String>` mutable vào `Set.copyOf`, rồi gọi `source.add("C")`. `copy` có xuất hiện `"C"` không?

**Đáp án:** Không, nếu `"C"` chỉ được thêm sau lúc `copyOf` hoàn thành. Snapshot không phản ánh thay đổi cấu trúc nguồn về sau.

**Bài 3.** Vì sao `Collections.unmodifiableSet(hashSet)` không phải nguồn tương đương `Set.of(...)` về tính ổn định nội dung?

**Đáp án:** Wrapper unmodifiable vẫn đọc qua `hashSet`, nên caller giữ `hashSet` có thể thay đổi membership qua tham chiếu khác. `Set.of` không có một mutable backing set như thế. Vì vậy không được mặc định runtime reuse view đó như một snapshot ổn định.

**Bài 4.** Kết quả `Set.copyOf(List.of("x", "x", "y"))` có mấy phần tử?

**Đáp án:** Hai phần tử (`"x"`, `"y"`). `Set.copyOf` không ném ngoại lệ chỉ vì nguồn Collection có duplicate.

**Bài 5.** `Set.copyOf(List.of("A", null))` có thành công không?

**Đáp án:** Không; `List.of` tự ném NPE ngay lúc tạo vì `null`. Nếu dùng `Arrays.asList("A", null)` rồi `Set.copyOf(...)`, lỗi NPE xuất hiện ở lời gọi `Set.copyOf`.

**Bài 6.** Nếu phần tử là đối tượng mutable mà field tên đổi sau `Set.copyOf`, có chắc kết quả Set “không thay đổi về mọi mặt” không?

**Đáp án:** Không. Tập không đổi về thao tác thêm/xóa qua API Set, nhưng trạng thái phần tử có thể đổi. Nếu field đó ảnh hưởng `equals`/`hashCode`, hành vi của Set có thể trở nên không xác định theo hợp đồng.

**Bài 7.** Đo `source == Set.copyOf(source)` trả `true` trong một JDK. Bạn có được sửa code để bắt buộc identity này trong unit test trên mọi JDK không?

**Đáp án:** Không. Đó là một quan sát implementation-specific; unit test nên dựa vào equality, membership và tính không sửa được.

**Bài 8.** Vì sao `Set.copyOf` không tự giải quyết concurrency khi source `HashSet` bị sửa từ luồng khác?

**Đáp án:** `Set.copyOf` không cam kết sao chép atomically từ dữ liệu bị sửa đồng thời. Muốn snapshot nhất quán, cần cơ chế bảo vệ/truyền trạng thái phù hợp.

## 17. Checklist áp dụng nhanh

- [ ] Tôi thực sự cần **tập không sửa được**, chứ không phải tập mutable hay danh sách giữ thứ tự/duplicate.
- [ ] Tôi hiểu `Set.copyOf` là API của **Java 10+** và vẫn hoạt động trong JDK hiện đại.
- [ ] Tôi phân biệt rõ **API contract** với *Implementation Note* về khả năng reuse.
- [ ] Nếu nguồn là `Set.of`/`Set.copyOf`, tôi biết runtime có thể bỏ qua copy thừa, nhưng không kỳ vọng `==`.
- [ ] Nếu nguồn mutable, tôi dựa vào **snapshot** thay vì chia sẻ cùng nguồn.
- [ ] Nếu nguồn là `Collections.unmodifiableSet`, tôi kiểm tra backing có thể thay đổi hay không.
- [ ] Tôi không dùng `Set.copyOf` như một phép deep-copy phần tử.
- [ ] Phần tử có `equals`/`hashCode` ổn định khi nằm trong Set.
- [ ] Tôi xác định chính sách `null` và duplicate của dữ liệu.
- [ ] Tôi không đặt giả định về thứ tự duyệt.
- [ ] Tôi không dùng collection value-based làm khóa `synchronized` hoặc làm ID.
- [ ] Nếu concurrency hoặc hiệu năng là yêu cầu quan trọng, tôi kiểm thử và benchmark đúng hợp đồng trên môi trường mục tiêu.

## 18. Nguồn tham khảo chính thống

- [Java SE 25 — `Set.copyOf(Collection)` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): đặc tả kết quả không sửa được, không phản ánh thay đổi nguồn và *Implementation Note* về việc thường tránh copy từ unmodifiable Set.
- [Java SE 25 — `Set`, Unmodifiable Sets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): `Set.of`/`Set.copyOf`, value-based instances, thứ tự duyệt không cam kết, `null` và duplicate.
- [Oracle Java 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): giải thích snapshot, khả năng reuse và sự khác biệt so với view.
- [Java SE 25 — `Collections.unmodifiableSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): view đọc xuyên qua nguồn, không phải snapshot.
- [Java SE 25 — `Collection`, Unmodifiable Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): định nghĩa unmodifiable, shallow immutability và khả năng phần tử mutable.
- [Java SE 25 — `Objects.equals` và equality](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html): hỗ trợ đọc code kiểm tra giá trị và chính sách null.

**Kết luận:** `Set.copyOf` có thể **tái sử dụng một unmodifiable Set nguồn phù hợp** thay vì cấp phát tập mới. Nhưng chỉ các **thuộc tính của API** — dữ liệu đúng, không sửa cấu trúc, snapshot không thay đổi theo nguồn, chính sách `null` — mới là điều ứng dụng được dựa vào. **Không phụ thuộc identity, lớp triển khai, thứ tự duyệt hay giả định hiệu năng.**