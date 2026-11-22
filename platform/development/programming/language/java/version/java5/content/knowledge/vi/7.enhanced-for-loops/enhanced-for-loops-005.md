# Tự xây dựng lớp có thể duyệt bằng for-each

## 1. Xác định lớp muốn cho người dùng duyệt cái gì

Giả sử ta xây một lớp `Shelf<Book>` biểu diễn một dãy sách. Mã sử dụng mong muốn viết:

```java
for (Book book : shelf) {
    System.out.println(book.title());
}
```

Đây là đoạn minh họa với `shelf` là một đối tượng `Shelf<Book>` đã được tạo.

Để cú pháp đó hợp lệ, lớp không cần kế thừa `ArrayList` hay công khai danh sách lưu trữ bên trong. Nó cần thực hiện `Iterable<Book>` hoặc, nếu thiết kế tổng quát, `Iterable<T>`.

Trước khi viết phương thức, quyết định hợp đồng duyệt:

| Câu hỏi | Quyết định cho Shelf<T> trong bài |
| --- | --- |
| Phần tử được duyệt là gì? | Giá trị kiểu `T` |
| Thứ tự nào? | Thứ tự của nguồn khi tạo Shelf |
| Có lặp lại được không? | Có |
| Hai vòng lặp có độc lập không? | Có, mỗi vòng có bộ lặp riêng |
| Có hỗ trợ nguồn rỗng không? | Có |
| Có chấp nhận phần tử `null` không? | Không |
| Có cho phép xóa qua iterator không? | Không |
| Dữ liệu nguồn ngoài có thể sửa cấu trúc của Shelf không? | Không, Shelf giữ một snapshot cấu trúc |

Hợp đồng này giữ ví dụ nhỏ nhưng đủ rõ. Nó cũng tránh việc vừa dạy cú pháp Iterable vừa phải thiết kế cơ chế đồng bộ hoặc theo dõi mọi thay đổi cấu trúc.

Các đoạn mã dùng Java 17 trở lên và những API vẫn áp dụng trong Java hiện nay.

## 2. Bước đầu: khai báo implements Iterable<T>

Hình dạng lớp là:

```java
final class Shelf<T> implements Iterable<T>
```

Đây là phần đầu của khai báo, không phải chương trình độc lập.

`T` cho biết kiểu phần tử mà người dùng nhận được khi duyệt. Với `Shelf<Book>`, phần tử của vòng for-each có thể được nhìn như `Book`; với `Shelf<String>`, phần tử là chuỗi.

Phương thức phải cung cấp có chữ ký:

```java
@Override
public Iterator<T> iterator()
```

Các điểm cần đúng:

- Tên là `iterator`, không phải một tên tự đặt tương tự.
- Không nhận tham số.
- Trả `Iterator<T>` có kiểu phần tử phù hợp.
- Phải là `public` vì thực hiện phương thức public của interface.
- `@Override` giúp trình biên dịch kiểm tra có thực hiện đúng hợp đồng không.

Chỉ có một phương thức mang tên `iterator()` nhưng không thực hiện `Iterable` chưa làm lớp trở thành nguồn for-each hợp lệ. Java kiểm tra quan hệ kiểu đã khai báo, không chỉ tìm một phương thức theo tên.

Khả năng tham gia for-each được quy định trong [API Iterable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html).

### Không để iterator() trả null

`iterator()` phải cung cấp một bộ lặp hợp lệ. Nếu nguồn rỗng, trả một iterator mà `hasNext()` là `false`, không trả `null`.

For-each vẫn cần làm việc với bộ lặp ngay cả khi không có phần tử. Trả `null` chỉ làm vòng lặp gặp lỗi khi sử dụng nó.

## 3. Chọn cách lưu dữ liệu và bảo vệ quyền sở hữu

Ví dụ dùng:

```java
private final List<T> items;
```

Constructor nhận `Collection<? extends T>` rồi tạo một snapshot bằng `List.copyOf`.

Ý nghĩa:

- Nhận được nguồn có phần tử thuộc `T` hoặc kiểu con của `T`.
- Giữ thứ tự duyệt của collection nguồn tại lúc tạo snapshot.
- Không cho người giữ danh sách nguồn sửa cấu trúc của Shelf qua alias.
- Không cho `null` là phần tử.
- Không có phương thức thay đổi cấu trúc Shelf sau khởi tạo.

Với nguồn `ArrayList<Book>`, nếu bên ngoài gọi `clear()` sau khi tạo Shelf, Shelf vẫn giữ hai cuốn sách đã nhận.

`List.copyOf` cung cấp danh sách không cho thêm, xóa hoặc thay thế phần tử. Đây là hợp đồng của [List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

### Snapshot cấu trúc không phải sao chép sâu

Các đối tượng phần tử vẫn có thể được dùng chung giữa nguồn và Shelf. Nếu `T` là một kiểu có trạng thái thay đổi được, một thay đổi bên trong đối tượng đó có thể được thấy khi duyệt.

Trong chương trình, `Book` là record gồm một `String` và một `int` nên không có trạng thái phần tử có thể sửa qua các thành phần ấy. Không suy ra mọi `Shelf<T>` đều bất biến sâu với mọi kiểu `T`.

### size() là tiện ích riêng, không phải điều kiện của for-each

Lớp có thể cung cấp `size()` để người dùng hỏi số phần tử. Nhưng `Iterable` không bắt buộc phương thức đó.

Một lớp tạo phần tử khi cần vẫn có thể duyệt bằng for-each mà không lưu sẵn danh sách hoặc không biết tổng số phần tử. Ví dụ Shelf chọn một nguồn snapshot hữu hạn để tập trung vào quá trình tự xây bộ lặp.

## 4. Mỗi lần iterator() tạo một trạng thái duyệt mới

Dữ liệu và vị trí đang duyệt là hai thứ khác nhau.

`Shelf` giữ danh sách. Mỗi đối tượng `Cursor` giữ:

- Một tham chiếu tới danh sách ổn định cần duyệt.
- Một chỉ số `position` của riêng nó.

Trong `iterator()`:

```java
return new Cursor<>(items);
```

Mỗi lời gọi tạo một Cursor mới. Vì vậy, hai vòng lặp không đẩy vị trí của nhau.

Không đặt một trường chỉ số duyệt chung trong `Shelf` rồi để mọi iterator thay đổi cùng trường đó. Cách ấy làm vòng lặp lồng nhau hoặc các lần duyệt xen kẽ ảnh hưởng lẫn nhau.

Cũng không chỉ tạo một iterator duy nhất trong constructor rồi trả lại nó mãi nếu hợp đồng của lớp đã hứa các lần duyệt độc lập.

### Vì sao Cursor có tham số E riêng?

Ví dụ khai báo:

```java
private static final class Cursor<E> implements Iterator<E>
```

`Cursor` là lớp lồng nhau `static`, nên nó không tự lấy tham số kiểu `T` từ một đối tượng Shelf bao ngoài. Nó khai báo `E` riêng và nhận `List<E>` cần duyệt qua constructor.

Khi tạo `new Cursor<>(items)` từ `List<T>`, trình biên dịch liên kết kiểu phù hợp. Không cần dùng kiểu thô, không ép từng phần tử từ `Object` và không cần một tham chiếu ẩn tới toàn bộ đối tượng Shelf.

## 5. Cài đặt hasNext() và next() theo hợp đồng

### hasNext() chỉ trả lời còn phần tử không

Với vị trí ban đầu `0`:

```java
return position < items.size();
```

Nếu danh sách có hai phần tử:

| position | hasNext() | Phần tử sẽ được next() trả về |
| --- | --- | --- |
| `0` | `true` | Phần tử đầu |
| `1` | `true` | Phần tử thứ hai |
| `2` | `false` | Không còn |

Trong cách cài đặt này, kiểm tra không tăng `position`. Gọi `hasNext()` nhiều lần không bỏ qua dữ liệu.

### next() phải tự kiểm tra hết dữ liệu

```java
if (!hasNext()) {
    throw new NoSuchElementException("shelf exhausted");
}
return items.get(position++);
```

Đây là thân phương thức `next` trong ví dụ, không phải chương trình độc lập.

Thứ tự ý nghĩa:

1. Xác minh còn phần tử.
2. Lấy phần tử ở vị trí hiện tại.
3. Tiến chỉ số để lần sau nhận phần tử tiếp theo.

Dù for-each thường kiểm tra trước, `Iterator` là API công khai mà người khác có thể gọi trực tiếp. `next()` vẫn phải ném `NoSuchElementException` khi hết dữ liệu.

Không để lỗi hết dữ liệu rơi xuống thành `IndexOutOfBoundsException` từ danh sách. Đó không phải ngoại lệ mà hợp đồng `Iterator.next()` yêu cầu cho tình huống này.

Không trả `null` để báo hết. Trong những nguồn khác, `null` có thể là dữ liệu; trạng thái kết thúc phải được báo đúng bằng ngoại lệ.

Hợp đồng này nằm trong [API Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html).

## 6. Chương trình đầy đủ: Shelf<T> dùng được trong for-each

Lưu thành `CustomForEachClassDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.StringJoiner;

public class CustomForEachClassDemo {
    record Book(String title, int pages) {
        Book {
            Objects.requireNonNull(title, "title");
            if (pages <= 0) {
                throw new IllegalArgumentException("pages must be positive");
            }
        }
    }

    static final class Shelf<T> implements Iterable<T> {
        private final List<T> items;

        Shelf(Collection<? extends T> source) {
            this.items = List.copyOf(source);
        }

        int size() {
            return items.size();
        }

        @Override
        public Iterator<T> iterator() {
            return new Cursor<>(items);
        }

        private static final class Cursor<E> implements Iterator<E> {
            private final List<E> items;
            private int position;

            Cursor(List<E> items) {
                this.items = items;
            }

            @Override
            public boolean hasNext() {
                return position < items.size();
            }

            @Override
            public E next() {
                if (!hasNext()) {
                    throw new NoSuchElementException("shelf exhausted");
                }
                return items.get(position++);
            }
        }
    }

    static String titles(Iterable<Book> books) {
        StringJoiner result = new StringJoiner(", ");
        for (Book book : books) {
            result.add(book.title());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        List<Book> input = new ArrayList<>(List.of(
                new Book("Core", 120),
                new Book("API", 80)));
        Shelf<Book> shelf = new Shelf<>(input);
        input.clear();

        System.out.println("input size = " + input.size());
        System.out.println("shelf size = " + shelf.size());
        System.out.println("titles = " + titles(shelf));

        int totalPages = 0;
        for (Book book : shelf) {
            System.out.println(book.title() + ": " + book.pages());
            totalPages += book.pages();
        }
        System.out.println("total pages = " + totalPages);

        Iterator<Book> first = shelf.iterator();
        Iterator<Book> second = shelf.iterator();
        System.out.println("hasNext twice = "
                + first.hasNext() + " / " + first.hasNext());
        System.out.println("first = " + first.next().title());
        System.out.println("second = " + second.next().title());
        System.out.println("first again = " + first.next().title());
        System.out.println("first hasNext = " + first.hasNext());

        try {
            first.next();
        } catch (NoSuchElementException exception) {
            System.out.println("exhausted next rejected");
        }

        Iterator<Book> readOnly = shelf.iterator();
        readOnly.next();
        try {
            readOnly.remove();
        } catch (UnsupportedOperationException exception) {
            System.out.println("iterator removal unsupported");
        }

        int pairs = 0;
        for (Book left : shelf) {
            for (Book right : shelf) {
                pairs++;
            }
        }
        System.out.println("nested pairs = " + pairs);
        System.out.println("titles again = " + titles(shelf));

        Shelf<Book> empty = new Shelf<>(List.of());
        System.out.println("empty hasNext = " + empty.iterator().hasNext());
        try {
            empty.iterator().next();
        } catch (NoSuchElementException exception) {
            System.out.println("empty next rejected");
        }

        try {
            new Shelf<>(Arrays.asList(new Book("Valid", 10), null));
        } catch (NullPointerException exception) {
            System.out.println("null item rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror CustomForEachClassDemo.java
java CustomForEachClassDemo
```

Stdout:

```text
input size = 0
shelf size = 2
titles = Core, API
Core: 120
API: 80
total pages = 200
hasNext twice = true / true
first = Core
second = Core
first again = API
first hasNext = false
exhausted next rejected
iterator removal unsupported
nested pairs = 4
titles again = Core, API
empty hasNext = false
empty next rejected
null item rejected
```

`Shelf` nằm trong lớp chứa chương trình để ví dụ chỉ cần một tệp. Có thể tách nó ra tệp riêng khi sử dụng thực tế và chọn mức truy cập phù hợp với API muốn cung cấp.

Phần dữ liệu `Book` có quy tắc riêng: tiêu đề khác `null` và số trang dương. Những kiểm tra ấy thuộc hợp đồng của một cuốn sách, không phải điều kiện chung mà mọi kiểu `T` cần có để tham gia Iterable.

## 7. Kiểm tra thiết kế qua từng hành vi

### Duyệt theo kiểu phần tử

`Shelf<Book>` cung cấp `Iterator<Book>`. Vì vậy:

```java
for (Book book : shelf) {
    totalPages += book.pages();
}
```

giữ được thông tin `Book` ngay trong thân vòng lặp. Không có phép ép kiểu khi gọi `title()` hoặc `pages()`.

Hàm `titles` chỉ nhận `Iterable<Book>`. Nó không cần biết lớp nguồn là Shelf, List hay một nguồn khác có cùng hợp đồng phần tử.

### Nguồn ngoài không sửa cấu trúc Shelf

Sau `input.clear()`, `input size` là `0` nhưng `shelf size` vẫn là `2`. Đây là bằng chứng lớp không giữ danh sách nguồn có thể thay đổi làm chính cấu trúc nội bộ.

### Hai bộ lặp bắt đầu độc lập

`first` và `second` đều được tạo bằng lời gọi `shelf.iterator()` riêng. Mỗi bộ lặp nhận `Core` đầu tiên.

`first.next()` lần thứ hai trả `API` mà không buộc `second` cũng tiến. Chỉ số `position` thuộc từng đối tượng Cursor.

### Lặp lồng nhau hoạt động

Shelf có hai phần tử. Vòng ngoài có hai lượt; mỗi lượt vòng trong tạo một iterator mới và có hai lượt. Kết quả là bốn cặp.

Nếu chỉ số nằm chung trong Shelf hoặc mọi lời gọi trả lại một iterator đã dùng, kiểm tra này sẽ phát hiện một hành vi không đúng với hợp đồng duyệt độc lập.

### Lặp lại từ đầu

Sau những lần dùng iterator tường minh và vòng lặp lồng nhau, `titles(shelf)` vẫn trả `Core, API`.

Dữ liệu Shelf không bị “tiêu thụ” bởi một iterator cụ thể. Iterator là trạng thái của một lần duyệt, còn Shelf vẫn có thể cấp trạng thái mới.

### Nguồn rỗng vẫn cung cấp iterator

`new Shelf<>(List.of())` hợp lệ. `hasNext()` là `false` ngay từ đầu. Nếu vẫn gọi `next()`, nhận `NoSuchElementException` đúng hợp đồng.

### Không xóa qua bộ lặp

Cursor không ghi đè `remove()` nên dùng cách cài đặt mặc định của Iterator: ném `UnsupportedOperationException`.

Điều này phù hợp với Shelf không cho thay đổi cấu trúc. Không cần tự thêm một hàm `remove` giả vờ thành công hoặc âm thầm không làm gì.

## 8. Khi dữ liệu đã có iterator đúng, có thể ủy quyền

Ví dụ đầy đủ tự viết Cursor để làm rõ trạng thái và hợp đồng. Nếu lớp chỉ muốn duyệt danh sách theo đúng thứ tự vốn có, có thể thay toàn bộ cách tạo Cursor bằng:

```java
@Override
public Iterator<T> iterator() {
    return items.iterator();
}
```

Đây là phương thức thay thế bên trong lớp Shelf đã có trường `items`; không phải một lớp độc lập.

Cách này vẫn là tự xây một lớp có thể duyệt bằng for-each. Lớp của ta thực hiện `Iterable<T>`, còn bộ lặp được lấy từ cấu trúc đã có.

Với `items` được tạo bằng `List.copyOf`, iterator cũng không cung cấp quyền sửa cấu trúc danh sách.

### Chọn theo thuật toán duyệt cần thiết

Ủy quyền phù hợp khi:

- Thứ tự duyệt chính là thứ tự của cấu trúc nền.
- Cấu trúc nền đã có iterator đúng.
- Không cần lọc, biến đổi hoặc tính toán thêm khi lấy phần tử.

Tự viết iterator có ý nghĩa khi:

- Dữ liệu không được lưu trực tiếp dưới dạng collection.
- Cần một thứ tự duyệt riêng.
- Cần tạo phần tử theo yêu cầu.
- Cần duyệt một cấu trúc như cây hoặc đồ thị theo quy tắc cụ thể.

Không viết lại iterator chỉ để có thêm một lớp. Nếu đổi danh sách nền sang một cấu trúc mà `get(index)` không hiệu quả, việc gọi `get` lặp lại theo chỉ số có thể làm thuật toán chậm; iterator có sẵn của cấu trúc nền thường là lựa chọn cần xem xét.

## 9. Nếu muốn Shelf thay đổi được, phải thiết kế lại chính sách duyệt

Ví dụ dùng snapshot không đổi cấu trúc nên Cursor chỉ cần biết vị trí. Nếu thêm các phương thức `add` hoặc `remove` vào Shelf, cần trả lời thêm:

- Iterator nhìn dữ liệu ở thời điểm tạo hay nhìn cấu trúc đang thay đổi?
- Xóa một phần tử trước vị trí hiện tại có làm bỏ sót hoặc đọc lặp không?
- Thêm phần tử sau khi bắt đầu duyệt có được thấy không?
- Có cho sửa qua chính iterator không?
- Những thay đổi từ luồng khác được xử lý theo hợp đồng nào?

Các chính sách khác nhau có chi phí khác nhau: snapshot cho từng lần duyệt, bộ lặp dựa trên cấu trúc sống hoặc phát hiện một số thay đổi không hợp lệ.

Không chỉ thêm một trường `position` rồi coi tất cả trường hợp đã được xử lý. `Iterable` không tự định nghĩa chính sách biến đổi cấu trúc cho lớp của ta.

Cơ chế báo `ConcurrentModificationException` của một số tập hợp không phải cơ chế đồng bộ và không bảo đảm phát hiện mọi thay đổi sai. Nếu lớp cần dùng giữa các luồng, phải thiết kế hợp đồng đồng thời riêng.

## 10. Không cần thực hiện toàn bộ Collection

Mục tiêu “duyệt được bằng for-each” không đòi lớp có `add`, `remove`, `contains` hoặc mọi phương thức collection.

Kế thừa một lớp tập hợp chỉ để có for-each có thể vô tình mở ra nhiều đường sửa dữ liệu mà hợp đồng miền không muốn cho phép.

Với Shelf, thành phần bên trong là một danh sách, còn giao diện bên ngoài chỉ cung cấp các khả năng cần thiết. Đây là lý do thực hiện một interface nhỏ thường phù hợp với lớp miền hơn việc kế thừa cách cài đặt collection.

Nếu API thật sự cần hành vi của một tập hợp có thể thay đổi, khi đó hãy thiết kế theo hợp đồng tương ứng; không áp dụng một mẫu duy nhất cho mọi lớp.

## 11. Những lỗi thường gặp

| Lỗi | Biểu hiện | Cách sửa |
| --- | --- | --- |
| Có iterator() nhưng không implements Iterable | For-each không áp dụng cho kiểu lớp | Khai báo đúng interface |
| iterator() không public | Không thực hiện được phương thức interface do quyền truy cập yếu hơn | Dùng `public` và `@Override` |
| Trả Iterator<Object> cho Iterable<Book> | Mất hoặc sai kiểu phần tử | Giữ cùng kiểu phần tử xuyên suốt |
| iterator() trả null cho nguồn rỗng | Lỗi khi bắt đầu vòng lặp | Trả iterator rỗng hợp lệ |
| hasNext tăng vị trí không đúng | Kiểm tra thêm làm mất phần tử | Không tiêu thụ phần tử khi chỉ hỏi trạng thái |
| next không kiểm tra hết | Trả sai hoặc ném sai ngoại lệ | Ném `NoSuchElementException` |
| Mọi vòng dùng chung một chỉ số | Duyệt xen kẽ hoặc lồng nhau sai | Trạng thái thuộc từng iterator |
| Trả danh sách nền ra ngoài | Bên ngoài thay đổi cấu trúc không theo hợp đồng | Giữ đóng gói và công bố chính sách sở hữu |
| remove âm thầm không làm gì | Người dùng tin đã xóa nhưng dữ liệu không đổi | Hỗ trợ đúng hoặc từ chối bằng ngoại lệ phù hợp |

Một đối tượng có thể cố ý vừa là `Iterable` vừa là `Iterator` cho một giao thức tiêu thụ một lần, nhưng đó là hợp đồng khác. Không dùng thiết kế ấy cho Shelf khi đã hứa nhiều lượt duyệt độc lập.

## 12. Các hành vi nên kiểm tra khi hoàn thiện lớp

Không chỉ chạy một vòng for-each trên nguồn có nhiều phần tử. Các tình huống có giá trị kiểm tra gồm:

- Nguồn rỗng.
- Chỉ một phần tử.
- Gọi `hasNext` nhiều lần trước `next`.
- Gọi `next` trực tiếp.
- Gọi `next` sau khi đã hết.
- Hai iterator tiến xen kẽ.
- Vòng lặp lồng nhau trên cùng nguồn.
- Một lần duyệt mới sau khi lần trước kết thúc.
- Thao tác `remove` theo chính sách đã công bố.
- Thay đổi danh sách đầu vào sau khi lớp được tạo.

Chương trình minh họa đã trực tiếp quan sát các hành vi chính: snapshot đầu vào, các lần duyệt độc lập, kiểm tra hết dữ liệu, nguồn rỗng và xóa không được hỗ trợ.

Nếu nguồn mới có khả năng thay đổi hoặc có tài nguyên cần đóng, kiểm tra phải mở rộng theo chính sách cụ thể đó. For-each không tự đóng một tài nguyên chỉ vì lớp thực hiện Iterable.

## 13. Thực hành tự kiểm tra

### Bài 1: Chỉ thêm một phương thức iterator có đủ không?

**Đáp án:** chưa. Kiểu lớp phải thực hiện `Iterable<T>` phù hợp để dùng trực tiếp làm nguồn for-each.

### Bài 2: Đặt position ở đâu?

Nếu muốn hai vòng lặp trên Shelf độc lập, chỉ số vị trí nên thuộc Shelf hay Cursor?

**Đáp án:** Cursor của từng lần duyệt. Shelf giữ dữ liệu, Cursor giữ tiến trình.

### Bài 3: Nguồn rỗng

`iterator()` nên trả `null` hay một iterator có `hasNext() == false`?

**Đáp án:** một iterator hợp lệ với `hasNext()` là `false`. `next()` của nó phải ném `NoSuchElementException`.

### Bài 4: Danh sách nguồn bị clear

Tại sao Shelf trong chương trình vẫn có hai sách sau khi `input.clear()`?

**Đáp án:** constructor tạo snapshot cấu trúc bằng `List.copyOf`, nên thay đổi về sau của danh sách nguồn không sửa cấu trúc Shelf.

### Bài 5: Có bắt buộc tự viết Cursor không?

**Đáp án:** không. Nếu iterator của cấu trúc nền đã phù hợp, `iterator()` có thể ủy quyền cho nó. Tự viết khi cần hành vi duyệt riêng hoặc khi muốn hiểu và kiểm soát thuật toán đó.

### Bài 6: Thêm add vào Shelf có tự động an toàn không?

**Đáp án:** không. Cần thiết kế rõ dữ liệu mà iterator quan sát và cách xử lý thay đổi cấu trúc. Interface Iterable không tự cung cấp chính sách ấy.

Một lớp dùng tốt với for-each cần nhiều hơn một phương thức mang tên đúng: nó phải giữ kiểu phần tử, cấp bộ lặp theo hợp đồng, xử lý hết dữ liệu chính xác và bảo vệ những giả định về cấu trúc đang được duyệt.
