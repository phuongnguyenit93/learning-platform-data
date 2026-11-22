# Xóa lần xuất hiện đầu hoặc cuối và duyệt ngược

## 1. Bài toán: trùng giá trị nhưng khác vị trí

Trong một hàng đợi hai đầu (`Deque`), cùng một giá trị có thể xuất hiện nhiều lần. Giả sử danh sách mã tác vụ đang có thứ tự từ đầu đến cuối như sau:

```text
first / head                             last / tail
     A       B       A       C       A       D
```

Yêu cầu “xóa A” vẫn còn thiếu một quyết định: xóa A gần đầu nhất, A gần cuối nhất, hay mọi A? Nếu cần kiểm tra các tác vụ từ phía cuối, chương trình phải đổi hướng đọc nhưng chưa chắc được phép lấy chúng ra khỏi deque.

Bài này tập trung vào ba công cụ:

- `removeFirstOccurrence(value)`: xóa một lần xuất hiện khớp gần đầu nhất.
- `removeLastOccurrence(value)`: xóa một lần xuất hiện khớp gần cuối nhất.
- `descendingIterator()`: duyệt từ cuối về đầu, có thể kết hợp xóa phần tử vừa duyệt khi iterator hỗ trợ thao tác đó.

Mục tiêu là biết chọn đúng phần tử theo **giá trị và vị trí hiện tại**, biết đọc ngược mà giữ nguyên dữ liệu, và biết xóa trong lúc duyệt mà không làm sai quy tắc của iterator.

Các ví dụ sử dụng API có trong Java 17. `ArrayDeque` là lớp cài đặt chính; một ví dụ riêng dùng `LinkedList` để giải thích trường hợp có `null`. Không cần Spring Boot, thư viện ngoài hoặc môi trường máy chủ.

## 2. “Đầu”, “cuối” và “lần xuất hiện” có nghĩa gì?

### 2.1. Đầu và cuối là vị trí trong deque lúc gọi phương thức

Quy ước của bài là viết deque theo chiều `first → last`, tương ứng với thứ tự của iterator thông thường. Với:

```text
[A, B, A, C, A, D]
```

phần tử đầu là A bên trái; phần tử cuối là D bên phải. “A đầu tiên” là A khớp đầu tiên khi đi từ trái sang phải. “A cuối cùng” là A khớp cuối cùng theo cùng thứ tự đó; cũng chính là A gặp đầu tiên khi đi từ phải sang trái.

Có thể tạm đánh dấu ba A để theo dõi:

```text
[A₁, B, A₂, C, A₃, D]
```

Các chỉ số nhỏ ở đây chỉ là nhãn minh họa cho vị trí; cả ba phần tử vẫn mang giá trị `"A"`. Xóa lần xuất hiện đầu sẽ xóa A₁; xóa lần xuất hiện cuối sẽ xóa A₃.

Không suy ra “đầu tiên” là được tạo sớm nhất hoặc “cuối cùng” là được tạo muộn nhất. Nếu chương trình thêm phần tử mới bằng `addFirst`, phần tử mới lại nằm trước phần tử cũ. Quan hệ với thời gian chỉ đúng khi cách thêm phần tử của ứng dụng duy trì quan hệ đó.

### 2.2. Tìm theo giá trị khác lấy phần tử tại một đầu

Với dữ liệu `[A, B, A, C, A, D]`:

| Lệnh | Giá trị trả về | Deque sau lệnh |
| --- | --- | --- |
| `removeLastOccurrence("A")` | `true` | `[A, B, A, C, D]` |
| `removeLast()` | `"D"` | `[A, B, A, C, A]` |
| `removeFirstOccurrence("C")` | `true` | `[A, B, A, A, D]` |

Mỗi dòng trên bắt đầu từ một bản dữ liệu ban đầu riêng. Lệnh occurrence tìm phần tử bằng giá trị nên có thể xóa ở giữa deque. Lệnh `removeLast()` không nhận giá trị cần tìm; nó lấy chính phần tử đang ở cuối.

Đừng “tự tìm” A cuối bằng cách gọi `pollLast()` liên tiếp rồi bỏ qua các giá trị khác. Cách đó còn lấy cả D, C hoặc các phần tử không phải mục tiêu ra khỏi deque, làm thay đổi nhiều hơn yêu cầu.

## 3. Hai phương thức xóa lần xuất hiện

Chữ ký rút gọn:

```java
boolean removeFirstOccurrence(Object target);
boolean removeLastOccurrence(Object target);
```

Hai phương thức trả kết quả có xóa được một phần tử hay không:

| Tình huống | Kết quả | Thay đổi dữ liệu |
| --- | --- | --- |
| Có một hoặc nhiều phần tử khớp | `true` | Xóa đúng một phần tử khớp ở phía đã chọn |
| Không có phần tử khớp | `false` | Giữ nguyên |
| Deque rỗng, tìm một giá trị hợp lệ | `false` | Vẫn rỗng |
| Chỉ có một phần tử và phần tử đó khớp | `true` | Trở thành rỗng |

Đây là xóa theo giá trị. `false` không có nghĩa deque rỗng: deque có thể chứa nhiều phần tử khác và không có mục tiêu. Ngược lại, `true` không có nghĩa đã xóa mọi bản sao.

Sau một lần xóa, các phần tử còn lại vẫn giữ thứ tự tương đối của chúng. Ví dụ, xóa A ở giữa `[B, A, C]` cho `[B, C]`; B không đổi thành phần tử đứng sau C.

Hợp đồng `Deque` mô tả phép khớp qua `Objects.equals(target, element)`; `remove(Object)` tương đương xóa lần xuất hiện đầu. Xem [tài liệu Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#removeFirstOccurrence(java.lang.Object)).

### 3.1. Phải chọn đúng biến thể của remove

Có ba ý nghĩa dễ bị lẫn:

```java
// Đoạn lệnh minh họa; deque là một Deque<String> đã được tạo.
String head = deque.remove();                 // lấy/xóa phần tử đầu
boolean changed = deque.remove("A");           // xóa một A gần đầu nhất
boolean changedAtTail = deque.removeLastOccurrence("A");
```

`remove()` không có đối số trả một phần tử và báo `NoSuchElementException` nếu rỗng. `remove("A")` có đối số trả `boolean`, có thể tìm sâu vào giữa deque và trả `false` nếu không thấy A.

Với `Deque<Integer>`, lệnh `remove(1)` là xóa giá trị `Integer` 1 qua `remove(Object)`, không phải xóa chỉ số 1. Giao diện `Deque` không có `remove(int index)`.

Nếu khai báo biến bằng `LinkedList<Integer>` hoặc `List<Integer>`, tập phương thức được nhìn thấy khác: có cả `remove(int)`. Do đó phải đọc cả kiểu của biến và danh sách tham số, không suy luận từ đối tượng thực tế một cách riêng lẻ. Khi ý định là xóa theo giá trị trong deque, tên `removeFirstOccurrence` hoặc `removeLastOccurrence` giúp thể hiện ý định rõ ràng.

### 3.2. Một lần gọi chỉ giải quyết một lần xuất hiện

Với `[A, B, A]`, một lần `removeFirstOccurrence("A")` cho `[B, A]`. Nếu cần xóa tất cả A, yêu cầu đã khác. Có thể duyệt và xóa theo điều kiện; không nên đọc tên occurrence thành “xóa mọi phần tử bằng nhau”.

Lặp phương thức occurrence đến khi trả `false` có thể cho kết quả xóa hết, nhưng phải tìm lại sau mỗi lần gọi. Phần chi phí ở cuối bài giải thích vì sao cách đó có thể tốn nhiều công việc khi dữ liệu lớn.

## 4. Phép khớp: bằng giá trị, không nhất thiết cùng đối tượng

### 4.1. Không dùng == để dự đoán kết quả xóa đối tượng

Hai đối tượng khác nhau có thể bằng nhau theo `equals`. Trong chương trình chạy ở phần sau, hai giá trị:

```java
Token stored = new Token(7);
Token probe = new Token(7);
```

không có cùng tham chiếu nhưng bằng nhau, vì `Token` là `record Token(int id)`. Dùng `probe` làm đối số vẫn xóa được `stored` đang nằm trong deque.

Kết quả này phụ thuộc định nghĩa bằng nhau của kiểu phần tử. Lớp thông thường không tự có quy tắc “cùng mã là bằng nhau” chỉ vì có trường `id`. Nếu lớp chưa định nghĩa `equals` phù hợp, hai đối tượng được tạo riêng có thể không khớp dù in ra thông tin giống nhau.

Đối với record có nhiều thành phần, phép bằng mặc định xét tất cả thành phần. `record Job(int id, String state)` không mặc nhiên coi hai Job cùng `id` nhưng khác `state` là bằng nhau. Nếu yêu cầu nghiệp vụ là “xóa Job gần cuối nhất có mã 7, bất kể trạng thái”, nên dùng điều kiện `job.id() == 7` khi duyệt ngược.

### 4.2. Kiểu tham số Object không biến mọi giá trị giống nhau thành bằng nhau

Phương thức nhận `Object`, nên một số đối số sai kiểu vẫn biên dịch. Trong ví dụ:

```java
Deque<Integer> numbers = new ArrayDeque<>(List.of(10, 1, 20, 1));
boolean a = numbers.removeFirstOccurrence(1L); // Long, không khớp Integer 1
boolean b = numbers.remove(1);                // Integer 1, xóa lần đầu
```

`a` là `false`, `b` là `true`; còn lại `[10, 20, 1]`. Giá trị số viết giống nhau không đủ: `Integer.equals(Long)` không trả `true`.

Tương tự, tìm `"a"` không mặc định khớp `"A"`. Nếu cần bỏ qua hoa/thường hoặc so một trường riêng, dùng điều kiện do ứng dụng định nghĩa; không sửa kỳ vọng của occurrence thành so sánh gần đúng.

### 4.3. Không cần hashCode để chọn một lần xuất hiện trong deque

Phép xóa đang xét thứ tự và phép bằng của phần tử. Không nên suy luận cách tìm trong deque giống tìm một khóa trong bảng băm. Việc một lớp có `hashCode` giống nhau không có nghĩa các đối tượng bằng nhau; cũng không xác định phải xóa bản nào.

Một đối tượng có trường thay đổi được còn có thể thay đổi kết quả `equals` sau khi đã được thêm vào. Hãy xác định giá trị hiện tại nào cần khớp hoặc dùng một mã ổn định trong điều kiện tìm kiếm. Khi chương trình cần phân biệt hai tác vụ có cùng nội dung nhưng là hai lần gửi khác nhau, nên có mã lần gửi riêng thay vì chỉ dựa trên nội dung bằng nhau.

## 5. Chương trình chạy: xóa đầu, xóa cuối và so sánh giá trị

Lưu mã vào **DequeOccurrenceDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;

public class DequeOccurrenceDemo {
    record Token(int id) {}

    private static Deque<String> sample() {
        return new ArrayDeque<>(List.of("A", "B", "A", "C", "A", "D"));
    }

    public static void main(String[] args) {
        Deque<String> first = sample();
        System.out.println("initial: " + first);
        System.out.println("first A: " + first.removeFirstOccurrence("A"));
        System.out.println("after first A: " + first);

        Deque<String> last = sample();
        System.out.println("last A: " + last.removeLastOccurrence("A"));
        System.out.println("after last A: " + last);
        System.out.println("missing Z: " + last.removeLastOccurrence("Z"));
        System.out.println("after missing Z: " + last);

        Deque<String> alias = sample();
        System.out.println("remove A: " + alias.remove("A"));
        System.out.println("after remove A: " + alias);
        System.out.println("removeLast endpoint: " + alias.removeLast());
        System.out.println("after removeLast: " + alias);

        Deque<String> one = new ArrayDeque<>(List.of("A"));
        System.out.println("single A: " + one.removeLastOccurrence("A"));
        System.out.println("single now: " + one);
        System.out.println("empty first A: " + one.removeFirstOccurrence("A"));

        Token stored = new Token(7);
        Token probe = new Token(7);
        Deque<Token> tokens = new ArrayDeque<>(List.of(stored, new Token(8)));
        System.out.println("same reference: " + (stored == probe));
        System.out.println("equal value: " + stored.equals(probe));
        System.out.println("remove equal token: " + tokens.removeFirstOccurrence(probe));
        System.out.println("tokens left: " + tokens);

        Deque<Integer> numbers = new ArrayDeque<>(List.of(10, 1, 20, 1));
        System.out.println("remove 1L: " + numbers.removeFirstOccurrence(1L));
        System.out.println("remove 1: " + numbers.remove(1));
        System.out.println("numbers left: " + numbers);

        Deque<String> nullable = new LinkedList<>(Arrays.asList(null, "A", null, "B"));
        System.out.println("remove last null: " + nullable.removeLastOccurrence(null));
        System.out.println("nullable left: " + nullable);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 DequeOccurrenceDemo.java
java DequeOccurrenceDemo
```

Stdout chính xác:

```text
initial: [A, B, A, C, A, D]
first A: true
after first A: [B, A, C, A, D]
last A: true
after last A: [A, B, A, C, D]
missing Z: false
after missing Z: [A, B, A, C, D]
remove A: true
after remove A: [B, A, C, A, D]
removeLast endpoint: D
after removeLast: [B, A, C, A]
single A: true
single now: []
empty first A: false
same reference: false
equal value: true
remove equal token: true
tokens left: [Token[id=8]]
remove 1L: false
remove 1: true
numbers left: [10, 20, 1]
remove last null: true
nullable left: [null, A, B]
```

Điểm cần quan sát:

- Hai deque `first` và `last` được khởi tạo độc lập. Vì thế có thể so sánh trực tiếp tác động của xóa A gần đầu và xóa A gần cuối.
- Trong deque `last`, D vẫn ở cuối sau khi xóa A cuối. Phương thức đã tìm A nằm trước D, không lấy D ra.
- Tìm Z không thấy trả `false`, giữ nguyên dữ liệu.
- `remove("A")` chọn A gần đầu; sau đó `removeLast()` lấy D và trả chính D.
- Xóa một phần tử bằng một đối tượng record bằng giá trị vẫn thành công dù hai tham chiếu khác nhau.
- `LinkedList` trong ví dụ cuối chứa được `null` và xóa được lần xuất hiện cuối của `null`.

Các chương trình trong bài đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24.0.2. Cờ `--release 17` kiểm tra việc sử dụng ngôn ngữ/API mục tiêu Java 17 và sinh bytecode tương ứng; không có nghĩa JVM dùng để chạy đã trở thành Java 17.

## 6. Đọc kết quả theo biến đổi trạng thái

Một cách tự kiểm tra là tách ba câu: bắt đầu ở đâu, phần tử nào khớp trước theo hướng chọn, và phần còn lại giữ thứ tự gì.

Ví dụ độc lập:

```text
Ban đầu:                    [X, A, B, A, C]
removeLastOccurrence("A"):   tìm từ cuối gặp C, rồi gặp A
Kết quả trả về:             true
Sau lệnh:                   [X, A, B, C]
```

Không đảo deque trước khi tìm. Hướng tìm đủ để chọn đúng A. Cũng không dùng “phần tử lớn nhất” để giải thích lần xuất hiện cuối: cuối là vị trí, không phải thứ tự tăng/giảm của giá trị.

Với chuỗi thao tác liên tiếp, lần sau phải đọc trạng thái mới:

| Bước | Thao tác | Trả về | Trạng thái sau bước |
| --- | --- | --- | --- |
| 0 | Khởi tạo | — | `[A, B, A, C, A]` |
| 1 | `removeFirstOccurrence("A")` | `true` | `[B, A, C, A]` |
| 2 | `removeLastOccurrence("A")` | `true` | `[B, A, C]` |
| 3 | `removeLastOccurrence("A")` | `true` | `[B, C]` |
| 4 | `removeFirstOccurrence("A")` | `false` | `[B, C]` |

Ở bước 3, A duy nhất đồng thời là lần xuất hiện đầu và cuối. Bước 4 trả `false` nhưng deque vẫn có hai phần tử.

## 7. Duyệt ngược bằng descendingIterator

### 7.1. Đổi hướng quan sát, giữ nguyên thứ tự lưu trữ

`iterator()` đi từ `first` đến `last`; `descendingIterator()` đi từ `last` đến `first`. Đối chiếu [mô tả iterator của Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#descendingIterator()).

Với `[A, B, A, C]`:

```text
iterator():            A → B → A → C
descendingIterator():  C → A → B → A
deque sau khi chỉ đọc: [A, B, A, C]
```

Tên “descending” ở đây là ngược thứ tự trong deque. Nó không sắp xếp giảm dần. Deque số `[3, 1, 4]` được đọc ngược thành `4, 1, 3`, không phải `4, 3, 1`.

### 7.2. Vòng lặp cơ bản

Đoạn lệnh sau dùng `deque` đã có sẵn và cần import `java.util.Iterator`:

```java
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
}
```

`hasNext()` kiểm tra còn phần tử chưa đọc trong lượt duyệt này. `next()` trả phần tử tiếp theo theo hướng ngược và tiến iterator. Chỉ hai lệnh đó không xóa phần tử khỏi deque.

Khi không còn phần tử, `hasNext()` trả `false`; gọi tiếp `next()` báo `NoSuchElementException`. Đây khác với `pollLast()`, vốn lấy/xóa phần tử cuối và trả `null` khi rỗng.

Một iterator đã đi hết không tự quay lại đầu cho lượt tiếp theo. Muốn duyệt lại từ cuối, tạo `descendingIterator()` mới. Các vòng lặp thường không nên dùng `null` làm dấu dừng của `next()`: iterator có `hasNext()`, và một lớp cài đặt cho phép `null` có thể trả một phần tử `null` hợp lệ.

### 7.3. Cách viết ngắn dành cho chỉ đọc

Có thể dùng:

```java
// Đoạn lệnh minh họa, deque đã được tạo.
deque.descendingIterator().forEachRemaining(System.out::println);
```

Hành động ở đây chỉ in dữ liệu. Nếu cần điều kiện xóa và kiểm soát từng bước, dùng vòng `while` với iterator rõ ràng như phần tiếp theo.

`descendingIterator()` trả `Iterator<E>`, không trả `Iterable<E>`. Vì thế không thể đặt trực tiếp kết quả đó vào vế phải của enhanced for:

```java
// Ví dụ sai, không biên dịch:
for (String value : deque.descendingIterator()) {
    System.out.println(value);
}
```

Enhanced for trên `deque` vẫn dùng iterator thông thường và đi từ đầu đến cuối. Đổi tên biến vòng lặp hoặc tên biến deque không đổi hướng duyệt.

## 8. Xóa qua iterator: đúng phần tử vừa đọc

### 8.1. remove của iterator không nhận giá trị

Khi iterator hỗ trợ xóa:

```java
// Đoạn lệnh minh họa; deque là ArrayDeque<String> đã được tạo.
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("A".equals(value)) {
        iterator.remove();
        break;
    }
}
```

Lượt duyệt bắt đầu từ cuối. Gặp A đầu tiên theo hướng ngược thì `iterator.remove()` xóa chính phần tử A vừa được `next()` trả về. `break` bảo đảm chỉ xóa một phần tử.

Với `[A, B, A, C]`, iterator đọc C rồi A bên phải. Kết quả là `[A, B, C]`. Lúc gọi `remove()`, C vẫn là phần tử cuối của deque. Vì thế “phần tử được iterator trả gần nhất” không có nghĩa “phần tử cuối của deque”.

Nếu chỉ cần so bằng một giá trị, `removeLastOccurrence("A")` ngắn gọn hơn vòng lặp này. Iterator hữu ích khi cần điều kiện phong phú hơn, cần thu thập thông tin trong lúc đọc, hoặc cần chọn nhiều phần tử.

### 8.2. Trạng thái hợp lệ của iterator.remove()

Theo [hợp đồng Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()), mỗi lần `next()` thành công cho phép tối đa một lần `remove()`; hỗ trợ xóa là khả năng tùy chọn của iterator.

```text
Tạo iterator
    ↓
next() thành công
    ↓
có thể remove() một lần, hoặc bỏ qua
    ↓
next() thành công tiếp theo
    ↓
có thể remove() một lần tiếp theo
```

Với iterator của `ArrayDeque` trong bài:

| Chuỗi thao tác | Kết quả |
| --- | --- |
| Tạo iterator → `remove()` | `IllegalStateException` |
| `next()` thành công → `remove()` | Xóa phần tử vừa được trả |
| `next()` thành công → `remove()` → `remove()` | Lần xóa thứ hai báo `IllegalStateException` |
| `next()` thành công → `hasNext()` → `remove()` | `hasNext()` không đọc phần tử mới; vẫn xóa phần tử của `next()` trước đó |
| Iterator rỗng → `next()` | `NoSuchElementException` |

Một lớp cài đặt khác có thể không hỗ trợ `Iterator.remove()` và báo `UnsupportedOperationException`. Không quy khả năng của iterator `ArrayDeque` cho mọi iterator trong Java.

## 9. Chương trình chạy: duyệt ngược và xóa trong lúc duyệt

Lưu thành **DequeReverseDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class DequeReverseDemo {
    private static <E> List<E> reverseValues(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        Iterator<E> iterator = deque.descendingIterator();
        while (iterator.hasNext()) {
            result.add(iterator.next());
        }
        return result;
    }

    public static void main(String[] args) {
        Deque<String> deque = new ArrayDeque<>(List.of("A", "B", "A", "C"));
        System.out.println("forward: " + new ArrayList<>(deque));
        System.out.println("reverse: " + reverseValues(deque));
        System.out.println("after read: " + deque);

        Iterator<String> iterator = deque.descendingIterator();
        while (iterator.hasNext()) {
            String value = iterator.next();
            if ("A".equals(value)) {
                iterator.remove();
                break;
            }
        }
        System.out.println("after reverse remove one A: " + deque);
        System.out.println("reverse now: " + reverseValues(deque));

        Deque<Integer> numbers = new ArrayDeque<>(List.of(1, 2, 3, 4, 5, 6));
        Iterator<Integer> reverse = numbers.descendingIterator();
        while (reverse.hasNext()) {
            if (reverse.next() % 2 == 0) {
                reverse.remove();
            }
        }
        System.out.println("after reverse remove evens: " + numbers);

        Deque<String> empty = new ArrayDeque<>();
        Iterator<String> exhausted = empty.descendingIterator();
        System.out.println("empty hasNext: " + exhausted.hasNext());
        try {
            exhausted.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty next: " + ex.getClass().getSimpleName());
        }

        Iterator<String> state = deque.descendingIterator();
        try {
            state.remove();
        } catch (IllegalStateException ex) {
            System.out.println("remove before next: " + ex.getClass().getSimpleName());
        }
        System.out.println("next before remove: " + state.next());
        state.remove();
        try {
            state.remove();
        } catch (IllegalStateException ex) {
            System.out.println("remove twice: " + ex.getClass().getSimpleName());
        }
        System.out.println("after iterator state checks: " + deque);

        Deque<String> consumed = new ArrayDeque<>(List.of("A", "B", "C"));
        List<String> removed = new ArrayList<>();
        while (!consumed.isEmpty()) {
            removed.add(consumed.pollLast());
        }
        System.out.println("pollLast values: " + removed);
        System.out.println("after pollLast loop: " + consumed);
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 DequeReverseDemo.java
java DequeReverseDemo
```

Stdout chính xác:

```text
forward: [A, B, A, C]
reverse: [C, A, B, A]
after read: [A, B, A, C]
after reverse remove one A: [A, B, C]
reverse now: [C, B, A]
after reverse remove evens: [1, 3, 5]
empty hasNext: false
empty next: NoSuchElementException
remove before next: IllegalStateException
next before remove: C
remove twice: IllegalStateException
after iterator state checks: [A, B]
pollLast values: [C, B, A]
after pollLast loop: []
```

Hàm `reverseValues` tạo một `List` để dễ in và so sánh kết quả của hướng đọc. Hàm chỉ dùng `hasNext()` và `next()`, nên deque gốc giữ nguyên. Việc tạo danh sách là lựa chọn của ví dụ, không phải yêu cầu bắt buộc để duyệt ngược.

Đoạn xóa A dừng sau lần khớp đầu theo hướng ngược. Đoạn xóa số chẵn không có `break`, vì yêu cầu là xóa mọi số chẵn. Sau cùng, chỉ các số lẻ `[1, 3, 5]` còn lại theo thứ tự ban đầu.

Kiểm tra trạng thái iterator dùng một iterator mới trên `[A, B, C]`: gọi `remove()` quá sớm báo lỗi; `next()` trả C; xóa C thành công; xóa lại mà chưa gọi `next()` mới báo lỗi. Deque cuối cùng là `[A, B]`.

Vòng `pollLast()` ở cuối là đối chứng: cũng cho giá trị `C, B, A`, nhưng lấy hết các phần tử ra. Hai cách có thể in cùng thứ tự mà tạo trạng thái dữ liệu hoàn toàn khác nhau.

## 10. Áp dụng điều kiện: xóa phần tử phù hợp gần cuối nhất

### 10.1. Khi phép bằng của toàn đối tượng không diễn đạt yêu cầu

Giả sử deque giữ các tác vụ. Mỗi tác vụ có mã và trạng thái. Cần hủy một tác vụ gần cuối nhất có trạng thái chờ, chứ không cần xóa một đối tượng bằng toàn bộ một đối tượng mẫu.

Hàm sau là một **phương thức tiện ích đặt trong lớp của ứng dụng**, không phải chương trình độc lập. Cần import `Deque`, `Iterator` và `java.util.function.Predicate`:

```java
static <E> boolean removeLastMatching(
        Deque<E> deque, Predicate<? super E> condition) {
    Iterator<E> iterator = deque.descendingIterator();
    while (iterator.hasNext()) {
        E value = iterator.next();
        if (condition.test(value)) {
            iterator.remove();
            return true;
        }
    }
    return false;
}
```

Điều kiện sử dụng với deque chuỗi, không chứa `null`:

```java
// Đoạn lệnh minh họa trong một phương thức:
Deque<String> jobs = new ArrayDeque<>(
        List.of("WAIT-1", "RUN-1", "WAIT-2", "DONE-1"));
boolean removed = removeLastMatching(jobs, s -> s.startsWith("WAIT-"));
// removed == true
// jobs còn [WAIT-1, RUN-1, DONE-1]
```

Thứ tự kiểm tra là DONE-1, WAIT-2; gặp WAIT-2 thì xóa và trả về ngay. WAIT-1 vẫn tồn tại. Nếu bỏ lệnh kết thúc sớm và tiếp tục xóa, chương trình chuyển sang yêu cầu “xóa mọi tác vụ chờ”.

Hàm này giả định iterator hỗ trợ xóa, deque không bị sửa từ nơi khác trong lúc duyệt, và điều kiện không tự thêm/xóa phần tử khỏi deque. Với `ArrayDeque` sử dụng trong bài, hỗ trợ xóa qua iterator có sẵn. Điều kiện có thể ném ngoại lệ; khi cần xử lý lỗi nghiệp vụ, phải quyết định rõ có chấp nhận các thay đổi đã thực hiện trước lỗi hay không. Hàm xóa một phần tử ở trên chỉ gọi xóa sau khi điều kiện trả `true`.

### 10.2. Chọn hướng theo câu hỏi, chọn số lần xóa theo điều kiện dừng

| Yêu cầu | Hướng và cách kết thúc |
| --- | --- |
| Xóa một phần tử bằng mục tiêu, gần đầu nhất | `removeFirstOccurrence(target)` |
| Xóa một phần tử bằng mục tiêu, gần cuối nhất | `removeLastOccurrence(target)` |
| Xóa một phần tử thỏa điều kiện, gần đầu nhất | `iterator()`, xóa rồi dừng |
| Xóa một phần tử thỏa điều kiện, gần cuối nhất | `descendingIterator()`, xóa rồi dừng |
| Xóa mọi phần tử thỏa điều kiện | Duyệt và xóa từng phần tử khớp; không dừng sau một lần |
| Chỉ xem từ cuối về đầu | `descendingIterator()`, không gọi `remove()` |

Hướng của iterator quyết định phần tử nào được gặp trước. Lệnh dừng quyết định xóa một hay nhiều phần tử. Phương thức occurrence chỉ quyết định được theo phép bằng; nó không nhận một `Predicate`.

Nếu cần biết chính phần tử đã xóa thay vì chỉ một cờ `boolean`, vòng iterator cho phép giữ `value` trước khi xóa rồi trả hoặc xử lý nó theo hợp đồng của ứng dụng. Đừng cố ép kết quả `boolean` của `removeLastOccurrence` thành kiểu phần tử.

## 11. Ba thao tác “đọc ngược” có tác động khác nhau

### 11.1. Chỉ duyệt

Dùng `descendingIterator()` để ghi log, kiểm tra điều kiện hoặc tìm một phần tử gần cuối. Nếu chỉ đọc, không cần tạo một bản sao và không thay đổi thứ tự deque.

### 11.2. Tạo danh sách theo chiều ngược

Hàm `reverseValues` trong chương trình cho một danh sách mới. Thêm hoặc xóa phần tử trong danh sách mới không thêm/xóa phần tử của deque gốc.

Tuy nhiên, đó là sao chép các tham chiếu phần tử. Nếu phần tử là đối tượng thay đổi được, sửa chính đối tượng đó qua danh sách mới vẫn có thể được quan sát qua deque. “Danh sách riêng” không có nghĩa mọi đối tượng bên trong được sao chép sâu.

Danh sách kết quả cũng không tự theo dõi những lần thêm/xóa vào deque sau khi hàm kết thúc. Nếu cần một lần đọc nhất quán trong chương trình nhiều luồng, tạo danh sách riêng không tự biến quá trình đọc thành một thao tác nguyên tử.

### 11.3. Lấy hết từ cuối

`pollLast()` lặp đến hết dữ liệu là một phép tiêu thụ. Chỉ dùng khi yêu cầu cho phép deque bị rút cạn.

```java
// Đoạn lệnh minh họa: deque là ArrayDeque<String> do luồng hiện tại quản lý.
while (!deque.isEmpty()) {
    String value = deque.pollLast();
    System.out.println(value);
}
```

Với `[A, B, C]`, lệnh in C, B, A rồi deque rỗng. Nếu đây là danh sách công việc còn chờ xử lý, việc chỉ muốn “xem từ mới đến cũ” mà dùng đoạn này có thể làm mất toàn bộ hàng chờ.

Không dùng vòng kiểm tra rỗng rồi lấy phần tử này như một bảo đảm đồng bộ cho nhiều luồng. Điều kiện sử dụng một luồng trong chú thích là một phần của ví dụ.

## 12. Sửa dữ liệu khi đang duyệt

### 12.1. Dùng chính iterator đang duyệt để xóa

Ví dụ dễ sai:

```java
// Ví dụ sai về cách sửa khi iterator đang hoạt động:
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("A".equals(value)) {
        deque.removeLastOccurrence(value);
    }
}
```

Có hai vấn đề khác nhau.

Thứ nhất, thao tác xóa thực hiện qua deque thay vì iterator đang theo dõi lượt duyệt. Không tiếp tục dựa vào iterator đó sau kiểu sửa ngoài này. Với `ArrayDeque`, cơ chế phát hiện sửa đổi trong khi duyệt thường báo `ConcurrentModificationException`, nhưng không bảo đảm mọi lần sai đều ném ngoại lệ.

Thứ hai, `removeLastOccurrence(value)` tìm lại theo giá trị. Nó không diễn đạt trực tiếp “xóa đúng đối tượng mà iterator vừa trả”. Khi có phần tử bằng nhau, logic tìm lại và logic vị trí iterator có thể không chọn cùng lần xuất hiện trong những biến thể vòng lặp khác.

Cách đúng trong phạm vi ví dụ là `iterator.remove()`. Tương tự, vòng enhanced for cũng có một iterator phía sau; gọi `deque.remove(...)` trong thân vòng không làm biến mất vấn đề.

### 12.2. Ngoại lệ phát hiện lỗi không phải cơ chế đồng bộ

`ArrayDeque` không an toàn cho truy cập đồng thời nếu không có đồng bộ phù hợp. Hành vi fail-fast phát hiện lỗi theo khả năng tốt nhất; không được dùng việc “có hoặc không có ConcurrentModificationException” để chứng minh chương trình nhiều luồng đúng. Lớp này hỗ trợ các thao tác tùy chọn của `Iterator`, bao gồm xóa. Xem [tài liệu ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Trong ứng dụng một luồng, quy tắc thực hành đơn giản là: tạo iterator, đọc/xóa qua iterator đó, kết thúc lượt duyệt, rồi mới thực hiện những thay đổi khác. Nếu có tác vụ hoặc luồng khác có thể sửa deque cùng lúc, cần chọn lớp cài đặt và chính sách đồng bộ theo thiết kế ứng dụng; không suy ra chính sách của chúng từ ví dụ `ArrayDeque`.

Không đưa kết quả stdout cố định cho một chương trình cố tình sửa deque ngoài iterator rồi chờ ngoại lệ. Việc ngoại lệ xuất hiện ở bước nào không phải kết quả ổn định để học thuộc.

## 13. null, dữ liệu sai kiểu và chi phí tìm

### 13.1. null phụ thuộc lớp cài đặt

`ArrayDeque` không cho thêm phần tử `null`. `LinkedList` cho phép `null`; ví dụ chương trình đầu cho thấy xóa `null` cuối trong `[null, A, null, B]` để còn `[null, A, B]`. Đối chiếu [tài liệu LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

Không khái quát rằng mọi deque phải có cùng kết quả khi tìm/xóa mục tiêu `null`. Hợp đồng giao diện cho phép một số ngoại lệ tùy lớp cài đặt đối với đối số không được hỗ trợ. Tương tự, tham số `Object` không có nghĩa mọi lớp deque phải im lặng trả `false` trước mọi đối số sai kiểu.

Khi dùng một điều kiện trên deque có thể chứa `null`, phải xử lý nó theo nghiệp vụ:

```java
// Điều kiện minh họa dành cho deque có thể có null:
value -> value != null && value.startsWith("WAIT-")
```

Trong chương trình đầu, `Arrays.asList(null, "A", null, "B")` được dùng làm dữ liệu khởi tạo `LinkedList`. Thay nó bằng `List.of(null, ...)` sẽ lỗi ngay khi tạo danh sách, trước cả khi deque được tạo. Đây là một lỗi của bước chuẩn bị dữ liệu, không phải của phương thức occurrence.

### 13.2. Tìm phần tử ở giữa có thể phải đi qua nhiều phần tử

Với `ArrayDeque`, xóa theo giá trị như `removeFirstOccurrence` và `removeLastOccurrence` có chi phí tuyến tính trong trường hợp xấu, không có bảo đảm tìm một giá trị bất kỳ trong thời gian hằng số. Đổi hướng có thể làm gặp mục tiêu sớm hơn trên một dữ liệu cụ thể, nhưng không xóa được trường hợp phải tìm gần hết deque.

Chỉ đọc toàn bộ n phần tử bằng iterator cần n lần `next()`. Nếu chỉ xử lý lần lượt và không tích lũy kết quả, không cần tạo danh sách n phần tử phụ. Hàm `reverseValues` tạo danh sách nên dùng thêm bộ nhớ theo số phần tử trả về.

Đừng suy ra “duyệt một lượt rồi xóa bằng iterator luôn là O(n)”. Với `ArrayDeque`, một lần xóa ở giữa qua iterator có thể phải dịch chuyển phần tử. Nhiều lần xóa trong một lượt duyệt vẫn có thể làm tổng công việc lớn hơn tuyến tính. Tài liệu lớp liệt kê `iterator.remove()` trong nhóm thao tác tuyến tính; xem [đặc tính chi phí của ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Vòng gọi occurrence lặp nhiều lần cũng có thể tìm lại và dịch chuyển lặp lại, dẫn đến chi phí bậc hai trong trường hợp xấu. Nếu yêu cầu là lọc toàn bộ dữ liệu lớn, hãy cân nhắc thao tác lọc phù hợp của lớp đang dùng hoặc tạo deque kết quả theo đúng thứ tự mong muốn. Không đổi cấu trúc dữ liệu chỉ vì một ví dụ nhỏ; xác định tần suất tìm/xóa và đo trên khối lượng đại diện khi hiệu năng thực sự là yêu cầu.

## 14. Lỗi phổ biến và cách tự chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách sửa suy luận |
| --- | --- | --- |
| Xóa mất D khi muốn bỏ A gần cuối | Dùng `removeLast()` | Xóa theo giá trị bằng `removeLastOccurrence("A")` |
| Vẫn còn một A sau lệnh | Nghĩ occurrence xóa tất cả | Một lần gọi xóa tối đa một phần tử |
| Hai đối tượng nhìn giống nhau nhưng không khớp | Quy tắc `equals` không theo điều kiện cần tìm | Kiểm tra mô hình bằng nhau; dùng điều kiện theo trường khi phù hợp |
| Tìm 1 không thấy trong deque số nguyên | Đối số là `1L` hoặc kiểu khác | Kiểm tra kiểu của mục tiêu và kiểu phần tử |
| Duyệt “descending” không cho thứ tự giảm dần | Nhầm đảo hướng với sắp xếp | Viết thứ tự hiện tại rồi đọc từ phải sang trái |
| Muốn xem ngược nhưng deque rỗng sau đó | Dùng `pollLast()` lặp | Chỉ đọc bằng `descendingIterator()` |
| Xóa bằng iterator ngay lập tức bị lỗi | Chưa gọi `next()` | Phải đọc một phần tử thành công trước |
| Lần xóa thứ hai liên tiếp bị lỗi | Mỗi `next()` chỉ cho một lần `remove()` | Chỉ xóa một lần cho phần tử vừa đọc |
| Vừa duyệt vừa sửa bị lỗi hoặc kết quả khó dự đoán | Sửa deque ngoài iterator | Dùng iterator đang duyệt hoặc đổi thiết kế lượt xử lý |
| Gọi enhanced for với descendingIterator không biên dịch | Kết quả là `Iterator`, không phải `Iterable` | Dùng vòng `while (hasNext())` |

Một cách kiểm tra trên giấy là ghi riêng bốn thông tin: thứ tự deque trước lệnh, hướng đang đọc, phần tử vừa được iterator trả, và phần tử thực sự bị xóa. Không chỉ nhìn giá trị cuối cùng được in vì nhiều cách có thể in giống nhau nhưng làm thay đổi dữ liệu khác nhau.

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1: Một chuỗi lệnh trên dữ liệu trùng

Bắt đầu bằng `[A, B, A, C, A]`, thực hiện liên tiếp:

```java
removeFirstOccurrence("A");
removeLastOccurrence("A");
removeLastOccurrence("Z");
```

Mỗi lệnh trả gì và deque cuối cùng là gì?

**Lời giải:** lệnh một trả `true`, còn `[B, A, C, A]`; lệnh hai trả `true`, còn `[B, A, C]`; lệnh ba trả `false`, không đổi. Deque cuối là `[B, A, C]`. Z không tồn tại không đồng nghĩa deque rỗng.

### Bài 2: Từ “cuối” trong ba thao tác

Deque là `[A, B, A, C]`. Iterator ngược gọi `next()` hai lần, rồi `remove()`. Phần tử nào bị xóa?

**Lời giải:** hai giá trị đọc được là C rồi A bên phải. `remove()` xóa A vừa đọc; deque thành `[A, B, C]`. C vẫn ở cuối. Nếu gọi `deque.removeLast()` thay thế sẽ xóa C và là một thao tác khác.

### Bài 3: Đọc ngược không phải sắp xếp

Deque số là `[3, 1, 4]`. Chỉ duyệt bằng `descendingIterator()` rồi in deque. Hai kết quả là gì?

**Lời giải:** lượt duyệt trả `4, 1, 3`; deque vẫn là `[3, 1, 4]`. Không có bước so sánh để sắp xếp và không có bước xóa.

### Bài 4: Một phần tử và trạng thái iterator

Deque là `[X]`. Iterator ngược gọi `hasNext()`, `next()`, `remove()`, rồi `hasNext()`. Điều gì xảy ra? Gọi thêm `remove()` thì sao?

**Lời giải:** lần kiểm tra đầu là `true`; `next()` trả X; xóa thành công khiến deque rỗng; lần kiểm tra sau là `false`. Gọi `remove()` lần nữa mà chưa có `next()` thành công mới sẽ báo `IllegalStateException` với iterator `ArrayDeque`.

### Bài 5: Xóa theo một trường

Có ba record `Job(7, "WAIT")`, `Job(8, "WAIT")`, `Job(7, "DONE")` theo thứ tự đó. Cần xóa Job có mã 7 gần cuối nhất, không quan tâm trạng thái. Dùng đối tượng mẫu `Job(7, "WAIT")` với `removeLastOccurrence` có đúng ý không?

**Lời giải:** không. Phép bằng record xét cả mã và trạng thái, nên mẫu đó khớp Job đầu và không khớp Job cuối. Duyệt ngược với điều kiện `job.id() == 7`, xóa qua iterator rồi dừng sẽ chọn Job cuối có trạng thái DONE. Nếu yêu cầu thực sự là “Job mã 7 đang WAIT gần cuối nhất”, điều kiện phải bao gồm cả trạng thái.

### Bài 6: Chọn công cụ theo tác động dữ liệu

Cần hiển thị nhật ký từ mục gần cuối về đầu và giữ nguyên nhật ký. Một người dùng vòng `pollLast()` rồi lưu các giá trị vào danh sách. Kết quả hiển thị đúng; còn lỗi nào?

**Lời giải:** nhật ký gốc bị lấy hết phần tử. Dùng iterator ngược chỉ đọc hoặc hàm tạo danh sách theo chiều ngược như `reverseValues`. Việc giao diện hiển thị đúng không chứng minh trạng thái dữ liệu sau thao tác đúng.

## 16. Tài liệu đối chiếu

- [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): đối chiếu tên phương thức, hướng iterator, kiểu trả về và ý nghĩa occurrence.
- [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): quy tắc `next()`/`remove()` và khả năng xóa tùy chọn.
- [ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html): các đặc tính của lớp được dùng trong ví dụ.
- [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html): đối chiếu ví dụ chấp nhận `null`.

Khi áp dụng, hãy trả lời rõ ba câu trước khi viết lệnh: đang chọn theo giá trị hay điều kiện, ưu tiên phía đầu hay phía cuối, và muốn chỉ đọc hay thực sự xóa. Ba quyết định đó xác định đúng công cụ và giúp dự đoán trạng thái deque sau thao tác.
