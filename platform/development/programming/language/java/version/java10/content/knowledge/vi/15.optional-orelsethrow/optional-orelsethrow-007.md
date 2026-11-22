# Phối hợp kết quả tìm kiếm Stream với bước bắt buộc có giá trị

## 1. Mục tiêu của bài học

Khi dùng **Java Stream API** để tìm một phần tử đáp ứng điều kiện, câu lệnh `findFirst()` hoặc `findAny()` thường trả về một **`Optional<T>`**, không phải trực tiếp một `T`. Đây là cách Java mô tả việc **có thể không tìm thấy kết quả**. Nhưng có những điểm trong chương trình mà nghiệp vụ **bắt buộc phải có một giá trị**: phải tìm được tài khoản, cấu hình, bản ghi hoặc tài nguyên thì mới tiếp tục xử lý được.

Từ **Java 10**, `Optional.orElseThrow()` không tham số là cách diễn đạt ngắn gọn, rõ ý rằng **“nếu Optional có giá trị thì lấy giá trị, nếu không thì ném `NoSuchElementException`”**. Cũng có overload `orElseThrow(exceptionSupplier)` đã có từ Java 8 để ném ngoại lệ mang ý nghĩa nghiệp vụ.

Mẫu trọng tâm:

~~~java
T required = source.stream()
        .filter(item -> matches(item))
        .findFirst()
        .orElseThrow();
~~~

Hoặc, khi cần thông điệp và kiểu ngoại lệ riêng:

~~~java
T required = source.stream()
        .filter(item -> matches(item))
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("Required value not found"));
~~~

Hai đoạn trên là **mẫu cú pháp** với `T`, `source` và `matches` đại diện cho kiểu, dữ liệu, điều kiện cụ thể; chương trình chạy đầy đủ ở phần sau.

Sau bài học, bạn có thể:

- Xây dựng pipeline `filter → findFirst/findAny → Optional → orElseThrow` đúng nghĩa.
- Phân biệt **Stream rỗng**, **không phần tử nào qua bộ lọc** và **phần tử `null`**.
- Hiểu `findFirst` giữ encounter order nếu nguồn có thứ tự, trong khi `findAny` có thể chọn bất kỳ phần tử phù hợp nào.
- Biết khi nào dùng `orElseThrow()` mặc định, khi nào dùng `orElseThrow(Supplier<? extends X>)` với ngoại lệ nghiệp vụ.
- Hiểu cách hoạt động **lazy** của supplier, short-circuiting và checked exceptions.
- Tránh hiểu sai rằng “lấy phần tử đầu tiên” đồng nghĩa “chắc chắn duy nhất”, hoặc “lọc xong” nghĩa là đã xử lý mọi lỗi.
- Viết và chạy chương trình Java 17+ có kết quả xác định, bao gồm các tình huống tìm thấy, không tìm thấy, null và tìm kiếm song song.

Phạm vi nội dung là các cơ chế **vẫn còn áp dụng trong Java hiện nay**. Lịch sử phiên bản chỉ được nhắc để phân biệt tính năng Java 10 với những tính năng đã tồn tại trước đó.

## 2. Các API tham gia và mốc phiên bản

| API | Vai trò | Ra mắt |
| --- | --- | --- |
| `Stream.filter(Predicate)` | Giữ phần tử đáp ứng điều kiện. | Java 8 |
| `Stream.map(Function)` | Biến đổi phần tử trước khi tìm hoặc biến đổi giá trị sau tìm. | Java 8 |
| `Stream.findFirst()` | Chọn phần tử đầu theo encounter order nếu có, trả `Optional<T>`. | Java 8 |
| `Stream.findAny()` | Chọn một phần tử bất kỳ, trả `Optional<T>`; cố ý cho phép hành vi không xác định phần tử được chọn. | Java 8 |
| `Optional.orElseThrow()` | Lấy giá trị hoặc ném `NoSuchElementException`. | **Java 10** |
| `Optional.orElseThrow(Supplier<? extends X>)` | Lấy giá trị hoặc gọi supplier để tạo ngoại lệ `X` và ném nó. | Java 8 |
| `Optional.get()` | Lấy giá trị hoặc ném `NoSuchElementException`; vẫn tồn tại nhưng `orElseThrow()` thể hiện ý định rõ hơn. | Java 8 |
| `Optional.orElse(value)` | Trả giá trị có sẵn hoặc giá trị dự phòng. | Java 8 |
| `Optional.orElseGet(supplier)` | Chỉ tạo giá trị dự phòng khi Optional rỗng. | Java 8 |
| `Optional.isEmpty()` | Kiểm tra không có giá trị. | Java 11 |
| `OptionalInt.orElseThrow()` và tương tự cho primitive Optional | Lấy primitive hoặc ném nếu không có. | Java 10 |

**Tính năng trọng tâm của Java 10 ở đây là overload `Optional.orElseThrow()` không đối số.** Đừng ghi nhầm `findFirst` hoặc `orElseThrow(supplier)` là tính năng lần đầu xuất hiện trong Java 10. Cả hai vẫn là thành phần quan trọng trong cách phối hợp với API Java 10.

## 3. Hiểu luồng dữ liệu từ Stream đến giá trị bắt buộc

Một pipeline điển hình có thể hình dung:

~~~text
Collection / nguồn dữ liệu
          |
          v
        stream()
          |
          v
       filter(...)   <-- Loại các mục không đạt điều kiện
          |
          v
       findFirst()   <-- Terminal, chọn một mục hoặc không có
          |
          v
  Optional<T> present / empty
          |
          v
     orElseThrow()
       /       \
      /         \
 Có giá trị     Rỗng
    |             |
 Trả về T     NoSuchElementException
~~~

Nếu dùng `orElseThrow(() -> new DomainException(...))`, nhánh rỗng ném ngoại lệ do ứng dụng chọn thay vì `NoSuchElementException` mặc định.

Điều kiện kiểm tra:

- **Nguồn có ít nhất một phần tử thỏa bộ lọc**: `findFirst()`/`findAny()` có thể trả Optional chứa phần tử được chọn (giả sử phần tử được chọn khác `null`); `orElseThrow` trả phần tử đó.
- **Nguồn rỗng hoặc không phần tử nào thỏa điều kiện**: `findFirst()`/`findAny()` trả `Optional.empty()`; `orElseThrow()` ném `NoSuchElementException`.
- **Phần tử được chọn là `null`**: theo JavaDoc, `findFirst` hoặc `findAny` **ném `NullPointerException` ngay tại bước tìm**, không tạo một Optional chứa null để `orElseThrow` xử lý.
- **Predicate/mapper tự ném ngoại lệ**: ngoại lệ đó phát sinh trong pipeline, không được đổi thành “không tìm thấy” bởi `orElseThrow`.

**Cực kỳ quan trọng:** `orElseThrow()` kiểm tra **Optional nhận được sau tìm kiếm**. Nó không thay thế validation đầu vào, không tự sửa dữ liệu `null` và không bắt mọi lỗi xảy ra trước đó.

## 4. `findFirst()`: lấy phần tử đầu tiên theo encounter order

Với một `List` có thứ tự, `stream()` thông thường có **encounter order** của danh sách. Khi có nhiều ứng viên, `findFirst()` chọn ứng viên đầu tiên theo thứ tự ấy.

~~~java
var names = java.util.List.of("An", "Binh", "Chi", "Binh");

var first = names.stream()
        .filter(name -> name.startsWith("B"))
        .findFirst()
        .orElseThrow();

System.out.println(first); // Binh
~~~

Phân tích:

1. `List` nguồn có encounter order.
2. `filter` giữ hai lần xuất hiện của `"Binh"`.
3. `findFirst` chọn lần xuất hiện đầu, trả `Optional<String>` chứa `"Binh"`.
4. `orElseThrow()` lấy String đó.

Trường hợp không có kết quả:

~~~java
// Mã cố ý gây ngoại lệ ở bước orElseThrow():
var required = names.stream()
        .filter(name -> name.equals("Duy"))
        .findFirst()
        .orElseThrow(); // NoSuchElementException
~~~

**Tìm không thấy không phải là `null`.** Kết quả `findFirst` là một `Optional.empty()` hợp lệ; chỉ khi caller xác nhận “bắt buộc phải có giá trị” thì `orElseThrow` chuyển trạng thái rỗng thành ngoại lệ.

### 4.1. `findFirst` không tự tìm giá trị “tốt nhất”

“First” nghĩa là **đầu tiên theo thứ tự nguồn**, không phải theo điểm số hoặc thời gian mới nhất, trừ khi bạn đã định nghĩa/sắp xếp nguồn theo tiêu chí đó.

Ví dụ tìm tài khoản có điểm cao nhất:

~~~java
record Candidate(String name, int score) {}

var candidates = java.util.List.of(
        new Candidate("A", 70),
        new Candidate("B", 95),
        new Candidate("C", 80)
);

var best = candidates.stream()
        .max(java.util.Comparator.comparingInt(Candidate::score))
        .orElseThrow();

System.out.println(best.name()); // B
~~~

`Stream.max(comparator)` cũng trả `Optional`; vì thế `orElseThrow` vẫn phù hợp. Nếu mục tiêu là giá trị lớn nhất, `max` thể hiện ý định rõ hơn việc tự sort mọi phần tử rồi `findFirst`.

### 4.2. `findFirst` khi nguồn không có encounter order

Ví dụ lấy Stream từ một `HashSet` (không cam kết encounter order), `findFirst` **không có cơ sở để hứa một “phần tử đầu” cố định**. JavaDoc cho phép chọn bất kỳ phần tử nào nếu Stream không có encounter order.

Nếu thứ tự ảnh hưởng nghiệp vụ, dùng một nguồn ordered, hoặc tạo thứ tự tường minh bằng `sorted(comparator)` trước khi gọi `findFirst()`. Không đặt kiểm thử dựa trên thứ tự tình cờ của `HashSet`.

### 4.3. `parallelStream().findFirst()` vẫn có hợp đồng về thứ tự

~~~java
var first = java.util.List.of("A", "B", "C")
        .parallelStream()
        .findFirst()
        .orElseThrow();

System.out.println(first); // A
~~~

Dù các bước xử lý được thực thi song song, nguồn List có encounter order nên `findFirst` vẫn phải tìm phần tử đầu theo thứ tự. Tuy nhiên, yêu cầu duy trì thứ tự có thể khiến việc tìm trong parallel stream tốn chi phí hơn. **Parallel không tự động nghĩa là nhanh hơn.**

## 5. `findAny()`: ưu tiên tìm một phần tử phù hợp, không yêu cầu “đầu tiên”

`findAny()` cũng là terminal operation trả `Optional<T>`, nhưng **cố ý không bảo đảm chọn phần tử nào**. Nó cho phép implementation tối ưu cho việc tìm một kết quả trong xử lý song song.

~~~java
var accounts = java.util.List.of("A", "B", "C");

var found = accounts.parallelStream()
        .filter(name -> name.equals("B"))
        .findAny()
        .orElseThrow();

System.out.println(found); // B
~~~

Output `B` chắc chắn ở ví dụ này vì **chỉ có một ứng viên**. Ngược lại, nếu điều kiện cho phép cả ba phần tử:

~~~java
var any = accounts.parallelStream()
        .filter(name -> !name.isBlank())
        .findAny()
        .orElseThrow();
~~~

`any` có thể là `"A"`, `"B"` hoặc `"C"`. **Không** viết bài kiểm thử đòi `"A"` phải được chọn; ngay cả khi một lần chạy tuần tự cho `"A"`, `findAny` vẫn không hứa kết quả cố định.

| Mục đích | Nên cân nhắc |
| --- | --- |
| Lấy bản ghi đầu trong danh sách có thứ tự nghiệp vụ | `findFirst()` |
| Chỉ cần một bản ghi thỏa điều kiện, ứng viên nào cũng hợp lệ | `findAny()` |
| Chọn bản ghi có điểm/giá trị lớn nhất | `max(comparator)` |
| Chọn bản ghi có giá trị nhỏ nhất | `min(comparator)` |
| Chỉ hỏi có tồn tại ứng viên hay không | `anyMatch(predicate)` |
| Phải có **đúng một** kết quả, không được có nhiều | Quy tắc kiểm tra tính duy nhất riêng, không chỉ `findFirst()` |

Đối với parallel stream, `findAny` có thể cho phép giải phóng ràng buộc thứ tự, nhưng không có cam kết nó nhanh hơn trong mọi dữ liệu hay mọi JDK.

## 6. `Optional<T>` là trạng thái tìm kiếm, không phải giá trị `null`

`Optional<T>` là container có thể chứa **một giá trị khác `null`** hoặc không chứa giá trị.

~~~java
var present = java.util.Optional.of("Java");
var empty = java.util.Optional.<String>empty();

System.out.println(present.isPresent()); // true
System.out.println(empty.isEmpty());      // true, Java 11+
~~~

Với Stream, bạn không cần tự tạo Optional trước:

~~~java
java.util.Optional<String> maybe = java.util.List.of("An", "Binh")
        .stream()
        .filter(name -> name.startsWith("B"))
        .findFirst();
~~~

Đến đây, caller có **quyền quyết định**:

- Giữ `Optional<String>` để tầng trên xử lý trường hợp vắng mặt.
- Chọn một giá trị dự phòng có ý nghĩa.
- Ném ngoại lệ vì nghiệp vụ không thể tiếp tục.
- Chạy hành động khi có kết quả, không bắt buộc trích xuất giá trị.

**Không nên gán chính biến Optional thành `null`.** Theo JavaDoc, Optional được thiết kế chủ yếu làm **kiểu trả về** cho phương thức có khả năng không có kết quả. Nếu phương thức trả `Optional`, hãy trả `Optional.empty()` khi không thấy, không trả `null`.

## 7. Hai overload `orElseThrow` và khi nào nên dùng

### 7.1. `orElseThrow()`: không giá trị là lỗi chung

~~~java
var selected = java.util.List.of("A", "B")
        .stream()
        .filter("B"::equals)
        .findFirst()
        .orElseThrow();

System.out.println(selected); // B
~~~

Nếu Optional rỗng, `orElseThrow()` ném **`NoSuchElementException`**. Đây là phương thức **không đối số được thêm từ Java 10**; API này vẫn được khuyến nghị dùng thay cho `Optional.get()` khi bạn muốn thể hiện ý định “bắt buộc phải có”.

Phép so sánh:

~~~java
optional.get();         // vẫn hoạt động, rỗng -> NoSuchElementException
optional.orElseThrow(); // Java 10+, rỗng -> NoSuchElementException
~~~

Mã `optional` ở đây là biến Optional giả định. Hai lời gọi gần giống về kết quả, nhưng tên `orElseThrow` rõ hơn về nhánh lỗi.

### 7.2. `orElseThrow(exceptionSupplier)`: lỗi có ngữ cảnh nghiệp vụ

Ví dụ bắt buộc tìm tài khoản đang hoạt động:

~~~java
var account = accounts.stream()
        .filter(a -> a.id() == requestedId && a.active())
        .findFirst()
        .orElseThrow(() -> new java.util.NoSuchElementException(
                "Active account " + requestedId + " not found"));
~~~

Trong mã minh họa trên, `accounts`, `requestedId` và kiểu `Account` phải có định nghĩa phù hợp. Khi không thấy, ngoại lệ chứa thông điệp cụ thể để chẩn đoán. Overload nhận `Supplier` **đã tồn tại từ Java 8**, không phải được giới thiệu bởi Java 10.

Một số lựa chọn theo **contract ứng dụng**:

| Loại tình huống | Cách viết tham khảo | Ý nghĩa |
| --- | --- | --- |
| Không có phần tử bắt buộc, không cần mô tả thêm | `.orElseThrow()` | `NoSuchElementException` mặc định |
| Không tìm thấy bản ghi với ID cụ thể | `.orElseThrow(() -> new NoSuchElementException("id=" + id))` | Có ngữ cảnh |
| Vi phạm bất biến của hệ thống (đã chắc rằng cấu hình phải tồn tại) | `.orElseThrow(() -> new IllegalStateException("Missing required config"))` | Báo trạng thái hệ thống không đúng kỳ vọng |
| API quy định ngoại lệ miền nghiệp vụ riêng | `.orElseThrow(() -> new AccountNotFoundException(id))` | Ranh giới nghiệp vụ rõ ràng, khi exception class đã tồn tại |
| Không tìm thấy là kết quả bình thường | **Không vội dùng** `orElseThrow` | Giữ Optional hoặc dùng nhánh dự phòng hợp lý |

Không có một ngoại lệ đúng cho mọi ứng dụng. **“Không tìm thấy”** có thể là lỗi, có thể là trạng thái hợp lệ; chọn dựa trên contract của chức năng.

### 7.3. Supplier được gọi **lười** (*lazy*) chỉ khi Optional rỗng

~~~java
var value = java.util.Optional.of("A")
        .orElseThrow(() -> {
            System.out.println("supplier called");
            return new IllegalStateException("absent");
        });

// Trả "A"; không in "supplier called".
~~~

Nếu Optional có giá trị, supplier **không được gọi**. Điều đó vừa tránh tạo ngoại lệ không cần thiết, vừa cho phép nội dung ngoại lệ được xây dựng theo dữ liệu lúc thực sự thiếu.

Nếu Optional rỗng:

~~~java
// Ném IllegalStateException("absent") và in "supplier called" trước đó.
java.util.Optional.<String>empty()
        .orElseThrow(() -> {
            System.out.println("supplier called");
            return new IllegalStateException("absent");
        });
~~~

**Cảnh báo về null supplier:** nếu Optional rỗng và supplier là `null` hoặc supplier trả về `null`, `orElseThrow(supplier)` sẽ ném `NullPointerException`. Đừng cố dùng `() -> null` để biểu diễn “không muốn ném”.

### 7.4. Checked exception cũng được hỗ trợ

Chữ ký khái quát:

~~~java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

Ví dụ trong một phương thức khai báo `throws IOException`:

~~~java
static String requireLine(java.util.List<String> lines)
        throws java.io.IOException {

    return lines.stream()
            .findFirst()
            .orElseThrow(() -> new java.io.IOException("Input has no lines"));
}
~~~

`IOException` là **checked exception**; compiler yêu cầu bạn xử lý hoặc khai báo nó. Đây là khả năng của overload nhận supplier; `orElseThrow()` không đối số ném `NoSuchElementException` unchecked.

Không nên lạm dụng checked exception nếu contract không yêu cầu; ví dụ trên nhằm minh họa **kiểu ngoại lệ `X` được suy luận từ supplier**.

## 8. Phối hợp `filter`, `map` và bước bắt buộc giá trị

Có nhiều cách kết hợp, mỗi cách có ngữ nghĩa khác nhau.

### 8.1. Lọc đối tượng, chọn một đối tượng, rồi yêu cầu có giá trị

~~~java
var selected = accounts.stream()
        .filter(a -> a.id() == requestedId)
        .findFirst()
        .orElseThrow(() -> new java.util.NoSuchElementException(
                "Account " + requestedId + " not found"));
~~~

Pipeline trả **`Account`** (giả sử `accounts` là `List<Account>`). Nếu caller cần toàn bộ object, đây là mẫu rõ nghĩa.

### 8.2. Lọc, chiếu sang một thuộc tính, rồi bắt buộc có kết quả

~~~java
var name = accounts.stream()
        .filter(a -> a.id() == requestedId)
        .map(Account::name)
        .findFirst()
        .orElseThrow();
~~~

Pipeline trả **`String`** là tên của bản ghi được tìm. Tuy nhiên, nếu `Account::name` trả `null`, `findFirst` **có thể ném NPE khi chọn phần tử null**, trước khi chạy `orElseThrow`.

### 8.3. Lọc và chọn object trước, sau đó `Optional.map`

~~~java
var name = accounts.stream()
        .filter(a -> a.id() == requestedId)
        .findFirst()
        .map(Account::name)
        .orElseThrow();
~~~

Khác biệt tinh tế: `Optional.map` sử dụng cơ chế tương tự `Optional.ofNullable` cho giá trị mapper trả về. Vì vậy nếu một `Account` được tìm thấy nhưng `name()` trả `null`, kết quả của `Optional.map` trở thành **`Optional.empty()`** và `orElseThrow` ném **`NoSuchElementException`**, không phải NPE ở `findFirst`.

**Đây là hai hành vi khác nhau:**

| Đường đi | `name()` trả `null` | Lỗi |
| --- | --- | --- |
| `stream.map(Account::name).findFirst()` | Null là phần tử được chọn trong Stream | `NullPointerException` tại `findFirst` |
| `stream.findFirst().map(Account::name).orElseThrow()` | Optional.map chuyển kết quả null thành empty | `NoSuchElementException` tại `orElseThrow` |

Chọn cấu trúc theo ý nghĩa. Nếu **Account tồn tại nhưng name bị thiếu** là lỗi dữ liệu riêng, nên kiểm tra nó tường minh thay vì gộp chung với “Account không tồn tại”:

~~~java
var account = accounts.stream()
        .filter(a -> a.id() == requestedId)
        .findFirst()
        .orElseThrow(() -> new java.util.NoSuchElementException(
                "Account not found: " + requestedId));

var name = java.util.Objects.requireNonNull(
        account.name(), "Account name must not be null");
~~~

Như vậy thông báo phân biệt **không có bản ghi** và **bản ghi thiếu thuộc tính bắt buộc**.

### 8.4. `Optional.flatMap` khi mapper trả Optional

Giả sử một API trả `Optional<String>` cho email thay thế:

~~~java
static java.util.Optional<String> alternativeEmail(Account a) {
    return java.util.Optional.ofNullable(a.name());
}
~~~

Bạn có thể dùng:

~~~java
var email = accounts.stream()
        .findFirst()
        .flatMap(StreamRequiredValueDemo::alternativeEmail)
        .orElseThrow();
~~~

Đoạn trên chỉ minh họa ý tưởng khi các phương thức/kiểu được đặt trong class thích hợp; nếu `flatMap` nhận mapper trả **`null` thay vì `Optional`**, API ném **`NullPointerException`**. Mapper của `Optional.flatMap` phải trả một Optional thực sự (có thể rỗng).

Không nên nhầm `Optional.map` với `Stream.map`: mặc dù cùng tên, chúng có ngữ nghĩa xử lý `null` khác nhau.

## 9. Trường hợp `null` trong dữ liệu nguồn

`Optional` không chứa giá trị `null`. `Stream.findFirst` và `Stream.findAny` cũng không thể trả một `Optional` “present nhưng value null”. JavaDoc quy định: **nếu phần tử được chọn là `null`, phương thức tìm ném `NullPointerException`**.

Ví dụ:

~~~java
var stream = java.util.stream.Stream.<String>of(null, "A");
// stream.findFirst().orElseThrow(); // NPE phát sinh ở findFirst
~~~

Không nên hiểu lỗi này là `NoSuchElementException` vì **vẫn có một phần tử** trong Stream, nhưng phần tử được chọn là `null`, trái hợp đồng của `Optional`.

Nếu nghiệp vụ cho phép bỏ qua `null`:

~~~java
var found = java.util.stream.Stream.<String>of(null, "A")
        .filter(java.util.Objects::nonNull)
        .findFirst()
        .orElseThrow();

System.out.println(found); // A
~~~

Đặt `filter(Objects::nonNull)` **trước** việc gọi các thuộc tính phần tử hoặc `findFirst` nếu source có thể chứa phần tử `null`.

Nhưng **không mặc định lọc null luôn đúng nghiệp vụ**: nếu null là bằng chứng dữ liệu bị hỏng thì nên validation và báo lỗi, chứ không âm thầm chọn một bản ghi khác.

### 9.1. `Optional.ofNullable` và `findFirst` khác nhau

~~~java
var nullable = java.util.Optional.ofNullable((String) null);
System.out.println(nullable.isEmpty()); // true
~~~

`Optional.ofNullable(null)` được thiết kế để trả empty. Ngược lại, `Stream.of((String)null).findFirst()` được quy định ném NPE nếu null được chọn. Hai API có **chính sách null khác nhau**, không thay thế tùy tiện.

### 9.2. Đừng chỉ kiểm tra nguồn khác `null` rồi coi phần tử đã hợp lệ

~~~java
java.util.Objects.requireNonNull(accounts, "accounts");
// accounts có thể không null nhưng vẫn chứa một Account null.
~~~

Nếu predicate sử dụng `a.id()` trên một phần tử `a == null`, nó ném NPE **trước khi tới bước tìm**. Phải kiểm tra hoặc lọc các phần tử theo contract dữ liệu.

## 10. Không tìm thấy và phần tử không đạt bộ lọc là cùng Optional rỗng

Xét:

~~~java
record Account(int id, String name, boolean active) {}

var accounts = java.util.List.of(
        new Account(1, "An", true),
        new Account(2, "Binh", false)
);
~~~

Bài toán “bắt buộc phải tìm tài khoản đang hoạt động”:

~~~java
var active = accounts.stream()
        .filter(a -> a.id() == 2 && a.active())
        .findFirst()
        .orElseThrow(() -> new java.util.NoSuchElementException(
                "Active account 2 not found"));
~~~

Tài khoản ID 2 **có tồn tại**, nhưng `active=false`, nên bộ lọc loại nó. Optional rỗng và ngoại lệ nói rằng **không tìm thấy tài khoản hoạt động**. Không nên ghi thông điệp “Account 2 does not exist” nếu điều kiện lọc còn kiểm tra trạng thái/điều kiện quyền truy cập.

Nếu cần phân biệt “không tồn tại” với “tồn tại nhưng chưa kích hoạt”, hãy thực hiện hai bước:

~~~java
var account = accounts.stream()
        .filter(a -> a.id() == 2)
        .findFirst()
        .orElseThrow(() -> new java.util.NoSuchElementException("No account 2"));

if (!account.active()) {
    throw new IllegalStateException("Account 2 is inactive");
}
~~~

**Nguyên tắc:** ngoại lệ tại `orElseThrow` phải phản ánh **đúng điều kiện tìm kiếm**, không khẳng định nguyên nhân mà pipeline không thể phân biệt.

## 11. `findFirst` không bảo đảm tính duy nhất

Một lỗi logic khác: khi nghiệp vụ đòi **chính xác một kết quả**, `findFirst()` hoặc `findAny()` đều **không kiểm tra xem có hai hay nhiều kết quả**.

~~~java
var values = java.util.List.of("A", "A", "B");
var one = values.stream()
        .filter("A"::equals)
        .findFirst()
        .orElseThrow(); // "A", không báo có hai phần tử khớp
~~~

Nếu dữ liệu cần duy nhất theo ID/email và bạn **không có ràng buộc duy nhất bảo đảm từ nguồn**, cần kiểm tra riêng:

~~~java
static <T> T requireExactlyOne(
        java.util.stream.Stream<T> source,
        java.util.function.Predicate<? super T> matches) {

    var candidates = source.filter(matches)
            .limit(2)
            .toList(); // Java 16+, dùng trong Java 17+

    if (candidates.isEmpty()) {
        throw new java.util.NoSuchElementException("No matching element");
    }
    if (candidates.size() > 1) {
        throw new IllegalStateException("More than one matching element");
    }
    return candidates.get(0);
}
~~~

`limit(2)` đủ để phân biệt 0, 1 và từ 2 ứng viên trở lên; không cần collect toàn bộ kết quả chỉ để phát hiện trùng. Nhưng **nguồn Stream đã bị tiêu thụ** ở `toList()`, không được dùng lại sau đó.

Nếu dữ liệu đến từ database và có unique constraint được bảo đảm, hãy tận dụng hợp đồng truy vấn và ràng buộc lưu trữ. Không nên chỉ dựa vào việc “lần này `findFirst` trả một phần tử” để chứng minh uniqueness.

## 12. `orElseThrow` so với fallback và xử lý tùy chọn

Tìm không thấy là **lỗi bắt buộc xử lý**, hay chỉ là một kết quả hợp lệ? Quyết định này phải được đưa ra trước khi chọn API.

| Ý định | API thường phù hợp | Hành vi khi Optional rỗng |
| --- | --- | --- |
| Bắt buộc phải có kết quả, lỗi chung | `orElseThrow()` | Ném `NoSuchElementException` |
| Bắt buộc phải có, lỗi có ngữ cảnh | `orElseThrow(() -> new X(...))` | Tạo và ném `X` |
| Không có thì dùng giá trị mặc định có sẵn | `orElse(defaultValue)` | Trả default |
| Không có thì tính/tra cứu giá trị mặc định | `orElseGet(supplier)` | Gọi supplier tạo value |
| Không có thì thử một nguồn Optional khác | `or(supplierOfOptional)` | Nhận Optional từ nguồn phụ |
| Có kết quả thì thực hiện hành động, không cần trả giá trị | `ifPresent(consumer)` | Bỏ qua khi rỗng |
| Chỉ kiểm tra có tồn tại hay không | `stream.anyMatch(predicate)` | Trả `false` nếu không có phần tử thỏa |
| Không tìm thấy là dữ liệu hợp lệ cho caller | Trả `Optional<T>` | Caller quyết định bước tiếp theo |

### 12.1. `orElse` có thể tính sẵn đối số dự phòng

~~~java
String fallback = expensiveDefault(); // được tính trước
String value = optional.orElse(fallback);
~~~

Nếu viết `optional.orElse(expensiveDefault())`, Java sẽ tính đối số `expensiveDefault()` trước khi gọi `orElse`, **kể cả khi Optional đã có giá trị**. Ngược lại:

~~~java
String value = optional.orElseGet(() -> expensiveDefault());
~~~

chỉ gọi supplier khi Optional rỗng.

Tương tự, `orElseThrow(() -> new X(...))` chỉ **gọi supplier tạo ngoại lệ khi rỗng**, trong khi code tạo exception trước rồi ném bằng logic thủ công có thể làm thêm công việc không cần thiết.

### 12.2. Khi nên giữ Optional thay vì ném ngay

~~~java
java.util.Optional<Account> maybeAccount = accounts.stream()
        .filter(a -> a.id() == id)
        .findFirst();
~~~

Nếu phương thức của bạn là `findAccount` với contract “có thể không tìm thấy”, trả Optional thường diễn đạt đúng hơn là ném. Chỉ biến Optional rỗng thành ngoại lệ tại **ranh giới mà tính bắt buộc thực sự được xác nhận**.

Điều này tránh trộn “tìm kiếm” với “chính sách lỗi” quá sớm và giúp caller quyết định có dùng fallback hay không.

## 13. Short-circuiting, lazy evaluation và side effect

`findFirst` và `findAny` là **short-circuiting terminal operations**. Chúng có thể dừng xử lý khi đã xác định được phần tử cần trả về. Vì vậy không được giả định `filter`, `map` hoặc `peek` sẽ được gọi **cho mọi phần tử**.

~~~java
var first = java.util.stream.Stream.of(1, 2, 3, 4)
        .filter(value -> value > 1)
        .findFirst()
        .orElseThrow(); // 2
~~~

Không có lý do phải xử lý đầy đủ các phần tử 3 và 4 sau khi đã xác định được kết quả đầu theo encounter order. Với parallel Stream, có thể có công việc được bắt đầu ở các nhánh khác, nên **không khẳng định số lần gọi predicate hay thứ tự thực thi chính xác**.

Các lambda trong pipeline nên:

- **Không can thiệp** vào nguồn đang được duyệt (*non-interfering*).
- **Không phụ thuộc mutable shared state** (*stateless*).
- Không dùng `peek` để thực hiện nghiệp vụ bắt buộc phải chạy trên tất cả phần tử.
- Không thay đổi nguồn trong lúc tìm, nhất là từ các luồng song song.

Ví dụ phản mẫu:

~~~java
// Không nên phụ thuộc vào số lần chạy filter để quyết định nghiệp vụ.
var calls = new java.util.concurrent.atomic.AtomicInteger();

var first = java.util.List.of(1, 2, 3)
        .parallelStream()
        .filter(value -> {
            calls.incrementAndGet(); // side effect chỉ minh họa
            return value > 1;
        })
        .findAny()
        .orElseThrow();
~~~

`AtomicInteger` giúp phép tăng counter là atomic, nhưng nó **không bảo đảm số lần predicate được gọi** hay làm Stream có thứ tự xác định. Việc đếm ở đây không nên là dữ liệu nghiệp vụ.

## 14. Mỗi Stream chỉ dùng cho một terminal operation

Một Stream pipeline sau khi chạy `findFirst` hoặc `findAny` đã được **tiêu thụ**:

~~~java
var stream = java.util.List.of("A", "B").stream();
var first = stream.findFirst();

// stream.findAny(); // không hợp lệ: Stream đã bị tiêu thụ
~~~

Muốn tìm lần nữa trên một collection, tạo **Stream mới**:

~~~java
var names = java.util.List.of("A", "B");

var first = names.stream().findFirst().orElseThrow();
var any = names.stream().findAny().orElseThrow();
~~~

Với nguồn I/O hoặc stream tài nguyên, còn cần đóng đúng cách khi nguồn yêu cầu, ví dụ dùng `try-with-resources`. `Optional.orElseThrow` không chịu trách nhiệm mở/đóng nguồn dữ liệu.

Một điểm dễ nhầm: **Stream lười**, nhưng sau khi đã bắt đầu terminal operation, nó thực sự xử lý pipeline; `orElseThrow` chỉ diễn ra **sau khi** terminal operation trả Optional. Không có việc `orElseThrow` tự chạy lại Stream để “thử tìm thêm”.

## 15. `IntStream`, `LongStream`, `DoubleStream` và Optional primitive

Đối với Stream primitive, phép tìm trả loại Optional chuyên biệt:

~~~java
var number = java.util.stream.IntStream.of(2, 4, 6)
        .filter(n -> n > 3)
        .findFirst()
        .orElseThrow();

System.out.println(number); // 4
~~~

`IntStream.findFirst()` trả `OptionalInt`; `OptionalInt.orElseThrow()` lấy `int` hoặc ném `NoSuchElementException`. Tương tự có `OptionalLong`, `OptionalDouble` với các Stream primitive.

Lợi ích: tránh boxing/unboxing không cần thiết trong những pipeline số học. Đừng cố gán kết quả tìm từ `IntStream` thành `Optional<Integer>` nếu không có bước chuyển đổi phù hợp; hai API khác loại.

Nếu `IntStream` sau lọc rỗng, `orElseThrow()` vẫn là bước “bắt buộc phải có số nguyên”.

## 16. Chương trình Java 17+ hoàn chỉnh đã kiểm chứng

Tạo tệp **`StreamRequiredValueDemo.java`**:

~~~java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamRequiredValueDemo {
    record Account(int id, String name, boolean active) {}

    static Account requireActive(List<Account> accounts, int id) {
        Objects.requireNonNull(accounts, "accounts");
        return accounts.stream()
                .filter(Objects::nonNull)
                .filter(a -> a.id() == id && a.active())
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(
                        "Active account " + id + " not found"));
    }

    public static void main(String[] args) {
        var accounts = List.of(
                new Account(1, "An", true),
                new Account(2, "Binh", false),
                new Account(3, "Chi", true));

        System.out.println("required=" + requireActive(accounts, 3).name());

        var firstActive = accounts.parallelStream()
                .filter(Account::active)
                .findFirst().orElseThrow();
        System.out.println("parallel first=" + firstActive.name());

        var uniqueAny = accounts.parallelStream()
                .filter(a -> a.id() == 3)
                .findAny().orElseThrow();
        System.out.println("unique any=" + uniqueAny.name());

        try {
            requireActive(accounts, 2);
        } catch (NoSuchElementException ex) {
            System.out.println("inactive=" + ex.getMessage());
        }

        try {
            accounts.stream().filter(a -> a.id() == 99)
                    .findFirst().orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("empty default=NoSuchElementException");
        }

        var supplierInvocations = new AtomicInteger();
        accounts.stream().filter(a -> a.id() == 1)
                .findFirst().orElseThrow(() -> {
                    supplierInvocations.incrementAndGet();
                    return new IllegalStateException("missing");
                });
        System.out.println("supplier after hit=" + supplierInvocations.get());

        try {
            accounts.stream().filter(a -> a.id() == 9)
                    .findFirst().orElseThrow(() -> {
                        supplierInvocations.incrementAndGet();
                        return new IllegalStateException("id=9 absent");
                    });
        } catch (IllegalStateException ex) {
            System.out.println("supplier miss=" + ex.getMessage());
        }
        System.out.println("supplier count=" + supplierInvocations.get());

        try {
            Stream.<String>of(null, "A").findFirst().orElseThrow();
        } catch (NullPointerException ex) {
            System.out.println("null selected=NullPointerException");
        }

        var safe = Stream.<String>of(null, "A")
                .filter(Objects::nonNull)
                .findFirst().orElseThrow();
        System.out.println("filtered null=" + safe);

        int primitive = accounts.stream()
                .mapToInt(Account::id)
                .filter(value -> value > 2)
                .findFirst().orElseThrow();
        System.out.println("primitive id=" + primitive);

        var absent = accounts.stream().filter(a -> a.id() == 0).findFirst();
        System.out.println("empty optional=" + absent.isEmpty());

        var mapped = accounts.stream().filter(a -> a.id() == 3)
                .findFirst().map(Account::name).orElseThrow();
        System.out.println("mapped name=" + mapped);

        var mappedNull = accounts.stream().filter(a -> a.id() == 3)
                .findFirst().map(a -> (String) null);
        System.out.println("mapped null empty=" + mappedNull.isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamRequiredValueDemo.java
java StreamRequiredValueDemo
~~~

**Stdout chính xác:**

~~~text
required=Chi
parallel first=An
unique any=Chi
inactive=Active account 2 not found
empty default=NoSuchElementException
supplier after hit=0
supplier miss=id=9 absent
supplier count=1
null selected=NullPointerException
filtered null=A
primitive id=3
empty optional=true
mapped name=Chi
mapped null empty=true
~~~

### 16.1. Giải thích kết quả

1. **`required=Chi`:** `requireActive` tìm tài khoản ID 3 đang hoạt động; `orElseThrow(supplier)` trả chính `Account`.
2. **`parallel first=An`:** ordered List Stream chứa `An` là tài khoản active đầu tiên; `findFirst` giữ encounter order ngay cả khi xử lý parallel.
3. **`unique any=Chi`:** `findAny` không bảo đảm chọn ứng viên nào nếu có nhiều người khớp, nhưng ở đây chỉ ID 3 thỏa điều kiện nên kết quả là `Chi`.
4. **`inactive=...`:** ID 2 tồn tại nhưng không active; bộ lọc loại nó nên ngoại lệ mô tả chính xác “không tìm thấy tài khoản active”.
5. **`empty default=NoSuchElementException`:** overload `orElseThrow()` không tham số ném ngoại lệ mặc định nếu tìm không thấy ID 99.
6. **`supplier after hit=0`:** đã có kết quả, supplier không được gọi.
7. **`supplier miss=id=9 absent` và `supplier count=1`:** khi không có kết quả, supplier chạy một lần để tạo ngoại lệ có nội dung cụ thể.
8. **`null selected=NullPointerException`:** `findFirst` chọn null và ném lỗi **trước** `orElseThrow`.
9. **`filtered null=A`:** lọc null từ Stream trước khi chọn, tìm được `A`.
10. **`primitive id=3`:** `OptionalInt.orElseThrow()` trả số nguyên primitive `3`.
11. **`empty optional=true`:** không tìm thấy được biểu diễn hợp lệ là `Optional.empty()` trước bước yêu cầu giá trị.
12. **`mapped name=Chi`:** `Optional.map` chuyển từ `Account` sang `String` có giá trị.
13. **`mapped null empty=true`:** `Optional.map` trả empty khi mapper trả null.

Chương trình dùng API hiện hành, không phụ thuộc thứ tự lựa chọn không xác định của `findAny`, không dựa vào thứ tự HashSet và không kiểm thử thông điệp ngoại lệ nội bộ JDK.

## 17. Những lỗi lập trình thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gọi `get()` theo thói quen dù ý định “bắt buộc hoặc ném lỗi” | Tên không mô tả nhánh lỗi rõ bằng API hiện đại. | Dùng `orElseThrow()` khi muốn NSEE mặc định. |
| Dùng `orElseThrow()` cho trường hợp “không tìm thấy” bình thường | Biến trạng thái hợp lệ thành exception. | Trả Optional hoặc chọn fallback. |
| Khẳng định “không có Account” dù filter còn kiểm tra active | Thông báo sai ngữ nghĩa. | Mô tả chính xác điều kiện hoặc tách các bước kiểm tra. |
| Dùng `findAny` rồi kỳ vọng kết quả đầu theo List | `findAny` không cam kết lựa chọn. | Dùng `findFirst` nếu cần encounter order. |
| Dùng `findFirst` để chọn “tốt nhất” khi dữ liệu chưa sort | Đầu theo nguồn không phải max/min. | Dùng `max`/`min` hoặc sắp xếp trước. |
| Nghĩ `findFirst` xác minh tính duy nhất | Có thể có nhiều ứng viên phù hợp. | Kiểm tra số lượng hoặc unique constraint. |
| Nguồn chứa `null` và gọi `findFirst` trực tiếp | Phần tử được chọn null gây NPE. | Validation hoặc `filter(Objects::nonNull)` theo nghiệp vụ. |
| Nghĩ `orElseThrow` biến mọi lỗi trước đó thành NSEE | Predicate/mapper có thể ném lỗi riêng. | Chẩn đoán đúng bước gây lỗi. |
| Đặt `filter(Objects::nonNull)` sau bước `map(a -> a.name())` mà mapper đã dereference null | NPE phát sinh trước filter. | Lọc hoặc kiểm tra null **trước khi truy cập field**. |
| Tạo ngoại lệ dự phòng trước khi cần | Công việc thừa khi Optional có giá trị. | Truyền supplier lambda lazily. |
| Truyền supplier null hoặc supplier trả null | Khi Optional rỗng gây NPE. | Cung cấp supplier trả exception thực sự. |
| Dùng Stream lại sau `findFirst` | Stream đã bị tiêu thụ. | Tạo Stream mới từ nguồn nếu cần tìm lần nữa. |
| Dùng `peek` để bảo đảm kiểm tra mọi phần tử | Short-circuiting có thể không duyệt hết. | Dùng thao tác kiểm tra độc lập khi phải duyệt toàn bộ. |
| Gọi `parallelStream` với mutable shared state trong predicate | Race hoặc kết quả không đáng tin. | Stateless, non-interfering lambdas. |
| Đoán parallel luôn hiệu quả hơn | Giữ encounter order có thể làm tăng chi phí. | Benchmark với dữ liệu thực tế. |
| Đọc map getter `Optional.map` trả null rồi cho rằng object ban đầu không tồn tại | `Optional.map` có thể chuyển kết quả null thành empty. | Tách validation đối tượng và validation thuộc tính. |

## 18. Bài tập thực hành có đáp án

**Bài 1 — Tìm thấy**

~~~java
var values = java.util.List.of(2, 4, 6);
int answer = values.stream()
        .filter(n -> n > 3)
        .findFirst()
        .orElseThrow();
~~~

**Đáp án:** `answer == 4`. Bộ lọc giữ 4 và 6, ordered Stream chọn 4 trước.

**Bài 2 — Không có kết quả**

~~~java
var values = java.util.List.of("A", "B");
var result = values.stream()
        .filter("X"::equals)
        .findFirst()
        .orElseThrow();
~~~

**Đáp án:** `NoSuchElementException` tại `orElseThrow()` vì Optional rỗng; đây không phải NPE.

**Bài 3 — Supplier có chạy không?**

~~~java
var result = java.util.Optional.of("OK")
        .orElseThrow(() -> new IllegalStateException("missing"));
~~~

**Đáp án:** Trả `"OK"`, supplier **không được gọi** và không có exception nào được tạo bởi lambda.

**Bài 4 — `findAny` với nhiều ứng viên**

~~~java
var values = java.util.List.of("A", "B", "C");
var result = values.parallelStream().findAny().orElseThrow();
~~~

**Đáp án:** `result` là một trong các giá trị, **không cam kết** giá trị cụ thể. Nếu cần `"A"` là phần tử đầu, dùng `findFirst()` trên ordered Stream.

**Bài 5 — Trường hợp `null`**

~~~java
java.util.stream.Stream.<String>of(null, "X")
        .findFirst()
        .orElseThrow();
~~~

**Đáp án:** Ném `NullPointerException` tại `findFirst` vì phần tử được chọn null. `orElseThrow` chưa được gọi. Muốn bỏ null, lọc `Objects::nonNull` trước `findFirst`, nếu nghiệp vụ cho phép.

**Bài 6 — Tên mapper trả `null`**

~~~java
var text = java.util.Optional.of("A")
        .map(s -> (String) null);
System.out.println(text.isEmpty());
~~~

**Đáp án:** In `true`; `Optional.map` chuyển mapper trả null thành empty. Gọi `text.orElseThrow()` sau đó sẽ ném `NoSuchElementException`.

**Bài 7 — Bắt buộc đúng một bản ghi**

Một Stream chứa hai bản ghi cùng `id`, nhưng code gọi `filter(id)...findFirst().orElseThrow()` không báo lỗi. Tại sao?

**Đáp án:** `findFirst` dừng khi chọn được phần tử đầu, không kiểm chứng toàn bộ tính duy nhất. Cần unique constraint hoặc kiểm tra ít nhất hai kết quả (`limit(2).toList()`), rồi xử lý trường hợp có nhiều.

**Bài 8 — `orElseThrow` hay `orElseGet`?**

Một yêu cầu cấu hình có thể dùng default hợp lệ nếu không có. Có nhất thiết ném ngoại lệ không?

**Đáp án:** Không. Khi absence hợp lệ và có fallback, `orElseGet` có thể phù hợp. `orElseThrow` chỉ đúng khi contract yêu cầu không được thiếu.

**Bài 9 — Checked exception**

Một phương thức dùng `orElseThrow(() -> new java.io.IOException("missing"))` phải làm gì?

**Đáp án:** Khai báo `throws IOException` hoặc bắt ngoại lệ đó, vì overload supplier có chữ ký `throws X` với `X` được suy luận thành `IOException`.

**Bài 10 — Stream primitive**

~~~java
var result = java.util.stream.IntStream.of(5, 7)
        .filter(n -> n > 6)
        .findFirst()
        .orElseThrow();
~~~

**Đáp án:** `result` có kiểu `int` và bằng 7. `findFirst` của `IntStream` trả `OptionalInt`, không phải `Optional<Integer>`.

## 19. Checklist trước khi đưa vào dự án

- [ ] Tôi đã quyết định **không tìm thấy có phải lỗi hay không**; không ném chỉ vì muốn lấy dữ liệu cho tiện.
- [ ] Khi lỗi, tôi chọn `orElseThrow()` hoặc `orElseThrow(supplier)` đúng contract và thông điệp.
- [ ] Tôi phân biệt overload `orElseThrow()` **Java 10** với overload supplier từ **Java 8**.
- [ ] Tôi hiểu `findFirst()` theo encounter order, `findAny()` có thể chọn bất kỳ phần tử nào.
- [ ] Nếu cần bản ghi tốt nhất, tôi chọn comparator, `max` hoặc `min` đúng nghĩa.
- [ ] Nếu cần chính xác một bản ghi, tôi có ràng buộc duy nhất hoặc kiểm tra số lượng kết quả.
- [ ] Tôi đã xem xét nguồn hoặc phần tử `null`, và không che giấu lỗi dữ liệu bằng cách lọc bừa.
- [ ] Tôi không nhầm “lọc không khớp” với “bản ghi hoàn toàn không tồn tại”.
- [ ] Tôi biết `Optional.map` trả empty nếu mapper trả null; `Stream.findFirst` ném NPE nếu chọn null.
- [ ] Tôi chỉ tạo ngoại lệ **khi Optional rỗng** thông qua supplier nếu cần.
- [ ] Predicate/mapper không có side effect ảnh hưởng kết quả, nhất là khi parallel.
- [ ] Tôi không phụ thuộc `peek` hoặc số lần gọi predicate trong short-circuiting.
- [ ] Tôi không dùng lại một Stream đã bị terminal operation tiêu thụ.
- [ ] Nếu API xử lý tài nguyên, tôi dùng chiến lược quản lý vòng đời tài nguyên riêng.
- [ ] Với `IntStream`/`LongStream`/`DoubleStream`, tôi nhận diện đúng Optional primitive.
- [ ] Tôi đã biên dịch/chạy ví dụ và kiểm tra cả nhánh thành công, rỗng, dữ liệu null và exception tùy chỉnh.

## 20. Tài liệu tham khảo chính thức, vẫn còn hiệu lực

- [Java SE 25 — `Optional<T>` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): `orElseThrow()` (Since 10), `orElseThrow(Supplier)`, `get`, `map`, `flatMap`, `orElse` và `orElseGet`.
- [Java SE 25 — `Stream<T>` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `findFirst`/`findAny`, short-circuiting, nullable selected element, encounter order và pipeline.
- [Java SE 25 — `OptionalInt` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html): `orElseThrow()` cho kiểu primitive.
- [Java SE 25 — Stream package specification](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): reduction, non-interference, stateless operations, laziness và parallel execution.
- [Java SE 10 — `Optional` API](https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html): thời điểm xuất hiện của overload `orElseThrow()` không đối số.
- [Java SE 25 — `NoSuchElementException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NoSuchElementException.html): ngoại lệ mặc định khi Optional không có giá trị.

**Ghi nhớ cuối bài:** `findFirst()`/`findAny()` chuyển **kết quả tìm kiếm có thể vắng mặt** thành `Optional<T>`. `orElseThrow()` (Java 10+) chuyển Optional đó thành **giá trị bắt buộc** hoặc ném `NoSuchElementException`; overload supplier cho phép thông điệp và kiểu ngoại lệ phù hợp nghiệp vụ. Hãy kiểm soát điều kiện lọc, thứ tự nguồn, `null` và tính duy nhất **trước khi coi kết quả tìm kiếm là bắt buộc có giá trị**.