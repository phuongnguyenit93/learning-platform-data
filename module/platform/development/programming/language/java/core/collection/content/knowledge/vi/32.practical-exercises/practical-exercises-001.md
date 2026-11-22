# Thực hành tổng hợp: Quản lý danh sách có chèn, cập nhật, tìm kiếm và xóa trong Java

## 1. Bài toán và mục tiêu

Xây dựng một chương trình Java quản lý **danh sách sách** bằng Java Collections. Mỗi sách có **mã** (`id`), **tên** (`title`) và **năm xuất bản** (`year`). Đây là dữ liệu minh họa; có thể thay sách bằng sinh viên, sản phẩm hoặc công việc mà vẫn giữ nguyên nguyên lý quản lý danh sách.

Sau bài thực hành, bạn cần có khả năng:

- Dùng `List<T>` và `ArrayList<T>` để lưu các đối tượng cùng kiểu, giữ thứ tự và truy cập theo chỉ số.
- **Thêm cuối** và **chèn tại vị trí** được chỉ định, hiểu cách các phần tử phía sau dịch chuyển.
- **Cập nhật** phần tử theo mã định danh, không nhầm cập nhật với chèn mới.
- **Tìm kiếm** theo mã chính xác và tìm nhiều kết quả theo một phần tên, không phân biệt chữ hoa/chữ thường.
- **Xóa** đúng phần tử theo mã; xử lý trường hợp không tìm thấy.
- Kiểm soát mã trùng, dữ liệu không hợp lệ, vị trí vượt phạm vi và việc sửa danh sách từ bên ngoài.
- Hiểu độ phức tạp của từng thao tác để chọn cấu trúc dữ liệu phù hợp.

### Quy tắc nghiệp vụ

1. Mỗi sách có mã **duy nhất**. Mã `B01` khác `b01` (so sánh có phân biệt chữ hoa/chữ thường).
2. Mã, tên phải có nội dung sau khi bỏ khoảng trắng đầu/cuối; năm xuất bản là số nguyên dương.
3. Vị trí chèn là chỉ số **bắt đầu từ 0**. Với danh sách có `n` phần tử, chỉ số chèn hợp lệ là `0` đến `n`; còn chỉ số của phần tử hiện có là `0` đến `n - 1`.
4. Khi sửa sách, **mã giữ nguyên**; chỉ tên và năm xuất bản được cập nhật. Nếu không tồn tại mã, thao tác trả về `false`.
5. Tìm kiếm hoặc xóa mã không tồn tại phải cho kết quả xác định (`Optional.empty()` hoặc `false`), không làm hỏng danh sách.
6. Danh sách trả ra cho mã gọi là **bản chụp chỉ đọc**, tránh để bên ngoài tùy ý thêm/xóa và phá vỡ quy tắc mã duy nhất.

## 2. Vì sao chọn `ArrayList`?

`List<Book>` diễn tả giao diện thao tác với danh sách; `new ArrayList<>()` cung cấp cách cài đặt bằng mảng động. `ArrayList` giữ thứ tự chèn và cho phép truy cập `get(index)` nhanh. Nó phù hợp với bài toán quy mô nhỏ và vừa, nơi việc duyệt và tìm tuyến tính là chấp nhận được.

Ví dụ, ban đầu danh sách có `[B01, B03]`:

- `add(B02)` tạo `[B01, B03, B02]`: thêm **cuối**.
- `add(1, B02)` tạo `[B01, B02, B03]`: **chèn** tại vị trí 1, đẩy `B03` sang phải.
- `set(1, B02Moi)` **thay thế** phần tử đang ở vị trí 1; không đổi độ dài danh sách.
- `remove(1)` xóa phần tử ở vị trí 1, các phần tử phía sau dịch sang trái.

Điểm quan trọng: **mã sách là danh tính nghiệp vụ; chỉ số là vị trí hiện tại**. Sau một lần chèn hay xóa, chỉ số có thể đổi, vì vậy chương trình tìm theo mã rồi mới xác định vị trí cần cập nhật/xóa. Không sử dụng chỉ số lưu từ lần truy cập cũ để nhận diện một cuốn sách.

## 3. Chương trình hoàn chỉnh chạy với Java 17+

Tạo tệp `Main.java` chứa toàn bộ mã bên dưới. Ví dụ cố ý dùng dữ liệu xác định để bạn có thể đối chiếu đầu ra. `Book` là `record` bất biến; `BookManager` đóng gói danh sách và cung cấp các thao tác thêm, chèn, cập nhật, tìm kiếm, xóa.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;

public class Main {

    record Book(String id, String title, int year) {
        Book {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Mã sách không được trống");
            }
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Tên sách không được trống");
            }
            if (year <= 0) {
                throw new IllegalArgumentException("Năm xuất bản phải dương");
            }
            id = id.strip();
            title = title.strip();
        }
    }

    static final class BookManager {
        private final List<Book> books = new ArrayList<>();

        // Thêm sách vào cuối danh sách.
        void add(Book book) {
            Objects.requireNonNull(book, "book");
            rejectDuplicateId(book.id());
            books.add(book);
        }

        // Chèn trước phần tử đang ở index; index == size() nghĩa là thêm cuối.
        void insert(int index, Book book) {
            Objects.requireNonNull(book, "book");
            if (index < 0 || index > books.size()) {
                throw new IndexOutOfBoundsException("Vị trí chèn: " + index);
            }
            rejectDuplicateId(book.id());
            books.add(index, book);
        }

        // Trả về false khi không có mã tương ứng; giữ nguyên mã sách khi sửa.
        boolean update(String id, String newTitle, int newYear) {
            int index = indexOfId(id);
            if (index == -1) {
                return false;
            }
            Book replacement = new Book(id, newTitle, newYear);
            books.set(index, replacement);
            return true;
        }

        // Tra cứu theo mã chính xác.
        Optional<Book> findById(String id) {
            int index = indexOfId(id);
            return index == -1
                    ? Optional.empty()
                    : Optional.of(books.get(index));
        }

        // Tìm tất cả sách có tên chứa từ khóa, không phân biệt hoa/thường.
        List<Book> searchByTitle(String keyword) {
            Objects.requireNonNull(keyword, "keyword");
            String needle = keyword.strip().toLowerCase(Locale.ROOT);
            if (needle.isEmpty()) {
                return List.of();
            }

            List<Book> matches = new ArrayList<>();
            for (Book book : books) {
                if (book.title().toLowerCase(Locale.ROOT).contains(needle)) {
                    matches.add(book);
                }
            }
            return List.copyOf(matches);
        }

        // Xóa theo mã; không thay đổi danh sách nếu mã không tồn tại.
        boolean delete(String id) {
            int index = indexOfId(id);
            if (index == -1) {
                return false;
            }
            books.remove(index);
            return true;
        }

        // Trả về bản chụp chỉ đọc, không lộ danh sách nội bộ.
        List<Book> list() {
            return List.copyOf(books);
        }

        private void rejectDuplicateId(String id) {
            if (indexOfId(id) != -1) {
                throw new IllegalArgumentException(
                        "Mã sách đã tồn tại: " + id);
            }
        }

        private int indexOfId(String id) {
            Objects.requireNonNull(id, "id");
            for (int i = 0; i < books.size(); i++) {
                if (books.get(i).id().equals(id)) {
                    return i;
                }
            }
            return -1;
        }
    }

    public static void main(String[] args) {
        BookManager manager = new BookManager();

        manager.add(new Book("B01", "Effective Java", 2018));
        manager.add(new Book("B03", "Clean Code", 2008));
        manager.insert(1, new Book(
                "B02", "Java Concurrency in Practice", 2006));

        System.out.println("Sau khi chèn: " + manager.list());
        System.out.println("Cập nhật B03: "
                + manager.update("B03", "Clean Code - revised", 2009));
        System.out.println("Tìm mã B02: "
                + manager.findById("B02").orElseThrow());
        System.out.println("Tìm tên java: "
                + manager.searchByTitle("java"));
        System.out.println("Xóa B01: " + manager.delete("B01"));
        System.out.println("Còn lại: " + manager.list());
        System.out.println("Xóa mã lạ: " + manager.delete("B99"));

        try {
            manager.add(new Book("B02", "Duplicate", 2020));
        } catch (IllegalArgumentException ex) {
            System.out.println("Trùng mã: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

Đầu ra tương ứng (mỗi dòng dưới đây là **một dòng stdout**; những dòng dài có thể tự xuống dòng do độ rộng terminal):

```text
Sau khi chèn: [Book[id=B01, title=Effective Java, year=2018], Book[id=B02, title=Java Concurrency in Practice, year=2006], Book[id=B03, title=Clean Code, year=2008]]
Cập nhật B03: true
Tìm mã B02: Book[id=B02, title=Java Concurrency in Practice, year=2006]
Tìm tên java: [Book[id=B01, title=Effective Java, year=2018], Book[id=B02, title=Java Concurrency in Practice, year=2006]]
Xóa B01: true
Còn lại: [Book[id=B02, title=Java Concurrency in Practice, year=2006], Book[id=B03, title=Clean Code - revised, year=2009]]
Xóa mã lạ: false
Trùng mã: Mã sách đã tồn tại: B02
```

### Diễn giải luồng thực thi

1. `add` đưa `B01` và `B03` vào cuối: `[B01, B03]`.
2. `insert(1, B02)` đưa `B02` vào giữa: `[B01, B02, B03]`; không ghi đè `B03`.
3. `update("B03", ...)` tìm chỉ số của `B03` và gọi `set` với bản ghi mới. Vị trí và kích thước danh sách giữ nguyên.
4. `findById("B02")` trả về `Optional<Book>` chứa đúng một sách; `searchByTitle("java")` trả về cả `B01` và `B02` theo thứ tự danh sách.
5. `delete("B01")` xóa sách đầu, để lại `[B02, B03]`; xóa `B99` trả về `false` và không thay đổi dữ liệu.
6. Thêm lại `B02` bị chặn vì trùng mã; ngoại lệ được bắt ở ranh giới chạy thử để người dùng nhìn thấy lý do.

## 4. Hiểu từng thao tác CRUD

### 4.1. Thêm cuối và chèn có vị trí — Create

`books.add(book)` thêm vào cuối. `books.add(index, book)` chèn **trước** vị trí `index`. Nếu `index == books.size()` thì chèn cuối là hợp lệ, kể cả danh sách rỗng với `index == 0`. Nếu `index < 0` hoặc `index > size()`, cần báo lỗi; không tự ý đổi một vị trí không hợp lệ thành vị trí cuối.

Phần kiểm tra mã trùng đặt **trước khi sửa danh sách**. Như vậy, cùng mã sẽ không vô tình tạo ra hai bản ghi khiến `update` hoặc `delete` trở nên mơ hồ. Trong ví dụ, kiểm tra trùng dùng tìm tuyến tính; cách này đơn giản và giữ mọi dữ liệu trong một danh sách duy nhất.

### 4.2. Cập nhật theo mã — Update

Các bước: tìm chỉ số bằng `indexOfId(id)` → nếu `-1` thì trả về `false` → tạo `Book` mới đã được kiểm tra dữ liệu → `books.set(index, replacement)`. Vì `Book` là record bất biến, cập nhật nghĩa là **thay đối tượng tại đúng vị trí**, không thay trực tiếp trường của đối tượng.

`set(index, value)` khác `add(index, value)`: `set` giữ số lượng phần tử, còn `add` tăng số lượng thêm một. Khi sửa, không dùng `add` vì sẽ tạo bản ghi thừa và có thể làm trùng mã.

### 4.3. Tìm kiếm theo mã và theo tên — Read

- **Theo mã:** dùng `equals` để khớp chính xác và trả `Optional<Book>`. Bên gọi có thể dùng `orElse(...)`, `ifPresent(...)` hoặc `orElseThrow()` tùy việc không tìm thấy có phải lỗi hay không. Chỉ dùng `orElseThrow()` khi chắc mã tồn tại, như phần chạy thử.
- **Theo tên:** chuyển từ khóa và tên về chữ thường bằng `Locale.ROOT` rồi dùng `contains` để so khớp một phần; trả nhiều kết quả, giữ thứ tự của danh sách ban đầu. Từ khóa chỉ chứa khoảng trắng cho danh sách rỗng, tránh biến truy vấn trống thành “tìm tất cả” ngoài ý muốn.
- **Xem toàn bộ:** `list()` trả `List.copyOf(books)`. Đây là danh sách không cho sửa cấu trúc và là bản chụp tại thời điểm gọi; nó không tự cập nhật khi `BookManager` thay đổi về sau. Các phần tử `Book` cũng bất biến nên người gọi không thể sửa ngầm dữ liệu nội bộ qua tham chiếu của chúng.

### 4.4. Xóa theo mã — Delete

`indexOfId` xác định đối tượng theo mã, sau đó `books.remove(index)` loại bỏ đúng vị trí. Khi xóa phần tử đầu hoặc giữa, các phần tử sau dịch trái và chỉ số thay đổi. Hàm trả `true` nếu có sách được xóa; `false` nếu không có mã tương ứng. Không truyền thẳng mã `String` cho `remove(Object)` vì danh sách đang chứa `Book`.

Nếu cần xóa nhiều sách theo điều kiện, `removeIf` hoặc `Iterator.remove()` là lựa chọn phù hợp. Không nên gọi `books.remove(...)` trực tiếp trong vòng `for-each` trên cùng danh sách, vì đó là sửa cấu trúc trong khi bộ lặp đang duyệt và có thể phát sinh `ConcurrentModificationException`.

## 5. Kiểm tra biên và kiểm thử chức năng

Các tình huống tối thiểu cần thử, bên cạnh luồng thành công trong `main`:

| Tình huống | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Thêm vào danh sách rỗng | `add(B01)` | Danh sách có một sách |
| Chèn đầu | `insert(0, B00)` | `B00` đứng trước các sách cũ |
| Chèn cuối | `insert(size(), B99)` | `B99` đứng cuối |
| Chèn vượt phạm vi | `insert(-1, ...)` hoặc `insert(size()+1, ...)` | `IndexOutOfBoundsException`, danh sách không đổi |
| Trùng mã | Thêm/chèn sách có mã đã có | `IllegalArgumentException`, danh sách không đổi |
| Sửa thành công | `update("B03", ..., 2009)` | Thay tên/năm, giữ mã, giữ vị trí và số lượng |
| Sửa mã không tồn tại | `update("B99", ..., 2024)` | `false`, danh sách không đổi |
| Tìm mã không tồn tại | `findById("B99")` | `Optional.empty()` |
| Tìm tên không phân biệt hoa/thường | `searchByTitle("JAVA")` | Nhận các sách có tên chứa “java” |
| Từ khóa rỗng | `searchByTitle("   ")` | Danh sách kết quả rỗng |
| Xóa thành công | `delete("B01")` | `true`, chỉ xóa `B01` |
| Xóa lại cùng mã | `delete("B01")` lần nữa | `false` |
| Mã/tên rỗng hoặc năm ≤ 0 | `new Book(... )` | `IllegalArgumentException` |
| Cố thay đổi danh sách trả về | `manager.list().clear()` | `UnsupportedOperationException`; dữ liệu trong manager giữ nguyên |

Có thể tự bổ sung các lời gọi kiểm thử sau vào `main` **sau khi** đã chạy ví dụ gốc (không cần thêm thư viện kiểm thử):

```java
BookManager check = new BookManager();
check.insert(0, new Book("S1", "Java Basics", 2023));
if (check.list().size() != 1) {
    throw new AssertionError("Chèn vào danh sách rỗng thất bại");
}
if (check.update("S9", "Missing", 2024)) {
    throw new AssertionError("Không được sửa mã không tồn tại");
}
if (!check.findById("S1").isPresent()) {
    throw new AssertionError("Không tìm được sách vừa thêm");
}
if (!check.delete("S1") || check.delete("S1")) {
    throw new AssertionError("Xóa phải thành công đúng một lần");
}
System.out.println("Các kiểm tra bổ sung đã qua");
```

Đoạn trên là **mảnh mã chèn thêm bên trong `main`**, dùng chung các lớp `Book` và `BookManager` đã khai báo; không phải một tệp độc lập. Sau khi thêm, chỉ có thêm dòng `Các kiểm tra bổ sung đã qua` ở cuối đầu ra của chương trình.

### Bất biến cần giữ sau mọi thao tác

- Không có hai phần tử cùng `id`.
- Không có phần tử `null` hay sách vi phạm ràng buộc mã/tên/năm.
- Chèn tăng `size()` đúng 1; cập nhật giữ `size()`; xóa thành công giảm `size()` đúng 1.
- Thao tác không thành công vì không tìm thấy hoặc do tham số không hợp lệ không được âm thầm sửa danh sách.
- Thứ tự phần tử còn lại không bị đảo khi cập nhật hoặc xóa.

## 6. Độ phức tạp và lựa chọn mở rộng

Gọi `n` là số sách trong danh sách, `L` là độ dài tên hoặc từ khóa khi xét tìm kiếm chuỗi.

| Thao tác trong `BookManager` | Thời gian điển hình/trường hợp xấu | Giải thích |
| --- | --- | --- |
| `add` | `O(n)` | Việc thêm cuối vào `ArrayList` có chi phí trung bình phân bổ `O(1)`, nhưng kiểm tra trùng mã duyệt `O(n)` |
| `insert` | `O(n)` | Kiểm tra trùng và dịch các phần tử phía sau |
| `update` | `O(n)` | Tìm mã `O(n)`, thay tại chỉ số `O(1)` |
| `findById` | `O(n)` | Duyệt cho đến khi tìm thấy hoặc hết danh sách |
| `searchByTitle` | Khoảng `O(n × L)` | Duyệt `n` tên và so khớp chuỗi; chi phí thực phụ thuộc độ dài từng tên và thuật toán `contains` |
| `delete` | `O(n)` | Tìm mã và dịch phần tử sau khi xóa |
| `list` | `O(n)` | Tạo bản chụp bằng `List.copyOf` |

Bộ nhớ lưu sách là `O(n)`; mỗi lần trả danh sách kết quả hoặc bản chụp có thể dùng thêm `O(n)` bộ nhớ. Bảng tính thời gian thể hiện toàn bộ **hàm đang viết**, không chỉ lệnh `ArrayList.add` hay `set` bên trong.

Khi danh sách lớn và việc tra cứu theo mã xảy ra thường xuyên, cân nhắc kết hợp `List<Book>` để giữ thứ tự với `Map<String, Book>` để tìm theo mã nhanh hơn. Tuy nhiên, phải cập nhật **cả hai cấu trúc một cách nhất quán** ở mọi lần thêm, sửa và xóa. Với bài thực hành này, một `ArrayList` duy nhất dễ kiểm chứng hơn.

`ArrayList` không tự bảo đảm an toàn khi nhiều luồng cùng sửa; chương trình ví dụ chạy một luồng. Nếu dùng trong ứng dụng nhiều luồng, cần thiết kế đồng bộ hóa thích hợp thay vì giả định thao tác CRUD ở đây tự an toàn.

## 7. Lỗi thường gặp và cách tránh

1. **Nhầm chèn với ghi đè:** `add(index, x)` chèn, `set(index, x)` thay thế; kiểm tra `size()` sau mỗi thao tác.
2. **Dựa vào chỉ số để nhận diện phần tử:** chỉ số đổi sau chèn/xóa; hãy tìm theo mã ổn định.
3. **Không chặn trùng mã:** `update/delete` có thể chỉ xử lý bản ghi đầu tiên và bỏ sót bản ghi trùng; kiểm tra trước khi thêm.
4. **Dùng `==` để so sánh chuỗi:** dùng `String.equals`, vì `==` so sánh tham chiếu đối tượng.
5. **Đọc trực tiếp danh sách nội bộ:** trả `books` sẽ cho mã bên ngoài bỏ qua xác thực; sử dụng bản chụp chỉ đọc.
6. **Đổi nội dung trong vòng `for-each` theo cách không hợp lệ:** thao tác xóa cấu trúc nên dùng chỉ số sau khi đã tìm, `Iterator.remove()` hoặc `removeIf`.
7. **Xóa theo giá trị mà chưa hiểu `equals`:** `remove(Object)` so sánh đối tượng theo `equals`; với yêu cầu xóa theo mã, tìm chỉ số trước là rõ ràng hơn.
8. **Bắt mọi ngoại lệ rồi im lặng:** nhập sai hoặc chỉ số sai cần được báo rõ, trong khi không tìm thấy mã được thể hiện bằng `false`/`Optional.empty()` theo hợp đồng hàm.
9. **Dùng `List.of(...)` làm danh sách để sửa:** các danh sách tạo bởi `List.of` không hỗ trợ `add`/`set`/`remove`; sử dụng `new ArrayList<>()` để có danh sách thay đổi được.

## 8. Bài tập mở rộng tự làm

Sau khi ví dụ gốc chạy đúng, tự thực hiện lần lượt:

1. Thêm menu console bằng `Scanner`: xem danh sách, thêm cuối, chèn theo vị trí, sửa theo mã, tìm theo mã/tên, xóa theo mã và thoát. Kiểm tra số nhập vào trước khi gọi manager.
2. Viết chức năng `insertBeforeId(String existingId, Book newBook)`: tìm chỉ số của sách mốc rồi chèn sách mới; nếu sách mốc không có, trả trạng thái thất bại và không thay đổi danh sách.
3. Thêm tìm kiếm theo khoảng năm xuất bản, trả danh sách kết quả giữ thứ tự gốc.
4. Viết kiểm thử tự động (JUnit hoặc bộ kiểm tra độc lập) cho các trường hợp trong bảng ở mục 5, đặc biệt là mã trùng, chỉ số không hợp lệ và bất biến sau lỗi.
5. Nếu muốn tối ưu, dùng thêm `HashMap<String, Book>` và thiết kế phương án cập nhật đồng bộ giữa map và list; chứng minh rằng thêm/xóa không để lại dữ liệu lệch.

**Tiêu chí hoàn thành:** chương trình biên dịch và chạy bằng Java 17+, đủ bốn thao tác chính (chèn, cập nhật, tìm kiếm, xóa), có tình huống thành công và thất bại, bảo toàn mã duy nhất và thứ tự danh sách, thông báo kết quả rõ ràng, không cho bên ngoài sửa trực tiếp trạng thái nội bộ.