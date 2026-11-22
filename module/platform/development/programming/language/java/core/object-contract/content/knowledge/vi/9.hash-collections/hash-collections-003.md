# Thêm hai đối tượng bằng nhau vào `HashSet` trong Java

Khi đưa hai đối tượng **khác instance nhưng bằng nhau về giá trị** vào một `HashSet`, tập hợp chỉ giữ **một phần tử** — **nếu** lớp đối tượng thực hiện đúng hợp đồng `equals()` và `hashCode()`. Lần thêm đầu thường trả `true`; lần thêm đối tượng thứ hai, vốn được coi là trùng phần tử, trả `false`. Đây là hành vi cốt lõi của một **set**: không chứa phần tử trùng theo tiêu chí bằng nhau của nó.

Tuy nhiên, câu trả lời phụ thuộc vào nghĩa cụ thể của từ **“bằng nhau”**. Hai object có cùng nội dung chưa chắc `equals()` trả `true`, và dù `equals()` trả `true`, một `hashCode()` sai hợp đồng vẫn có thể khiến `HashSet` nhận cả hai. Bài học sẽ phân tích từng trường hợp, cùng các ví dụ Java 17 chạy được.

## 1. Kết quả chuẩn khi hai object bằng nhau

Giả sử có hai instance của cùng một kiểu, với cùng giá trị:

~~~java
Book first = new Book("978-1", "Java");
Book second = new Book("978-1", "Java");
~~~

Đây là **đoạn minh họa**; định nghĩa `Book` hoàn chỉnh xuất hiện ở chương trình bên dưới.

Hai biến `first` và `second` được tạo bằng hai lần `new`, nên `first == second` là `false`. Nếu `Book.equals()` so sánh hai trường `isbn`, `title`, thì `first.equals(second)` là `true`. Khi đưa chúng vào cùng một `HashSet<Book>`:

~~~java
Set<Book> books = new HashSet<>();
System.out.println(books.add(first));  // true
System.out.println(books.add(second)); // false
System.out.println(books.size());      // 1
~~~

Hai đoạn trên có thể đặt trong `main` với các import và định nghĩa `Book` phù hợp. Chúng minh họa ba điểm quan trọng:

- **`add(first) == true`:** tập hợp chưa chứa phần tử nào tương đương `first`, nên thêm thành công.
- **`add(second) == false`:** tập hợp đã chứa một phần tử tương đương `second`, nên không thêm bản sao logic.
- **`size() == 1`:** chỉ có một phần tử phân biệt theo quy tắc equality, mặc dù đã tạo hai instance.

Lần thêm trùng không làm tăng `size()` và **không thay thế instance đang có bằng instance truyền vào**. `HashSet` không phải bộ lưu tất cả các instance, và cũng không tự gộp thuộc tính từ hai đối tượng tương đương.

## 2. “Bằng nhau” không có nghĩa là `==`

Với biến thuộc kiểu **tham chiếu**:

| Phép kiểm tra | Ý nghĩa | Hai instance khác nhau cùng nội dung |
|---|---|---|
| `first == second` | Hai biến có trỏ tới cùng một object? | `false` |
| `first.equals(second)` | Hai object có bằng nhau theo định nghĩa của kiểu? | Có thể `true` |
| `first.hashCode() == second.hashCode()` | Hai object có mã băm trùng nhau? | **Bắt buộc `true` nếu equals là true** |
| `books.add(second)` | Có thêm được một phần tử mới, không trùng? | `false` khi set đã có phần tử tương đương và hợp đồng được tuân thủ |

`Object.equals()` mặc định chỉ coi hai tham chiếu cùng trỏ một instance là bằng nhau. Một lớp tự tạo **không** ghi đè `equals()` sẽ thừa hưởng nghĩa mặc định đó; khi ấy hai lần `new` dù cùng dữ liệu thường được coi là hai phần tử khác nhau của `HashSet`.

`String`, các wrapper thông thường, `BigInteger`, nhiều value object và Java `record` có định nghĩa equality theo nội dung. `record` tự sinh `equals()` và `hashCode()` theo các component. **Record không tự so sánh sâu phần tử của một component kiểu mảng**: nếu component là array, equality của array mặc định vẫn theo tham chiếu, trừ khi nhà phát triển có xử lý riêng.

## 3. Vai trò phối hợp của `hashCode()` và `equals()`

`HashSet` được triển khai dựa trên cấu trúc băm (`HashMap` trong JDK thông dụng). Khi thêm một phần tử khác `null`, tập hợp sử dụng `hashCode()` để định hướng vùng lưu/truy tìm, rồi dùng `equals()` để xác định khóa tương đương khi cần.

Có thể hình dung:

1. Tính hash của đối tượng định thêm.
2. Xác định vị trí/bucket ứng với hash theo tổ chức nội bộ hiện tại.
3. Kiểm tra trong vị trí phù hợp xem có phần tử trùng theo equality hay không.
4. Nếu **đã có phần tử trùng**, `add` trả `false`; nếu **chưa có**, ghi phần tử mới và trả `true`.

Đây là **mô hình khái niệm** để hiểu hành vi, không phải cam kết rằng mọi phiên bản JDK luôn dùng một số bucket hay một thứ tự gọi phương thức cố định. Chính sách tính bucket, xử lý collision, chuyển sang cấu trúc cây khi va chạm nhiều có thể là chi tiết triển khai.

Hợp đồng bắt buộc:

> Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` **phải** đúng.

Chiều ngược lại **không đúng**: nếu hash giống nhau, `a` và `b` vẫn có thể khác nhau. Collision là bình thường; `HashSet` không loại một phần tử chỉ vì `hashCode()` trùng, mà phải đối chiếu equality phù hợp.

Nếu ghi đè `equals()` nhưng **quên** ghi đè `hashCode()` tương ứng, tập hợp có thể lưu nhiều đối tượng mà ứng dụng cho là bằng nhau. Kết quả đó là hệ quả của **lớp vi phạm hợp đồng**, không phải quy tắc bình thường của `HashSet`.

## 4. Ví dụ Java 17 đầy đủ: trường hợp đúng, hash sai, collision và khóa mutable

Lưu chương trình sau vào **`HashSetEqualityDemo.java`**. Nó có bốn tình huống độc lập:

- `Book` là `record`, có equality/hash đúng theo hai thành phần.
- `BrokenKey` **cố ý viết sai**: `equals` theo `id` nhưng hash theo `salt`. Chỉ dùng để minh họa lỗi.
- `CollidingKey` luôn trả cùng hash `7` nhưng equality vẫn phân biệt `id`; đây là collision **hợp lệ**.
- `MutableKey` có trường được dùng làm hash có thể thay đổi; ví dụ minh họa lý do không sửa khóa sau khi thêm vào set.

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class HashSetEqualityDemo {

    record Book(String isbn, String title) {}

    static final class BrokenKey {
        private final String id;
        private final int salt;

        BrokenKey(String id, int salt) {
            this.id = id;
            this.salt = salt;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey b
                    && Objects.equals(id, b.id);
        }

        @Override
        public int hashCode() {
            return salt; // SAI: equals không so salt.
        }
    }

    record CollidingKey(String id) {
        @Override
        public int hashCode() {
            return 7; // Hợp lệ: object bằng nhau vẫn có cùng hash.
        }
    }

    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int newId) {
            this.id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey m && id == m.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Book first = new Book("978-1", "Java");
        Book equalBook = new Book("978-1", "Java");
        Book differentBook = new Book("978-2", "Concurrency");

        Set<Book> books = new HashSet<>();
        System.out.println("same reference: " + (first == equalBook));
        System.out.println("equal value: " + first.equals(equalBook));
        System.out.println("equal hash: "
                + (first.hashCode() == equalBook.hashCode()));
        System.out.println("add first: " + books.add(first));
        System.out.println("add equal: " + books.add(equalBook));
        System.out.println("size after equal: " + books.size());
        System.out.println("add different: " + books.add(differentBook));
        System.out.println("size after different: " + books.size());
        System.out.println("contains equal copy: "
                + books.contains(new Book("978-1", "Java")));

        BrokenKey brokenA = new BrokenKey("A", 1);
        BrokenKey brokenB = new BrokenKey("A", 2);
        Set<BrokenKey> broken = new HashSet<>();
        System.out.println("broken equals: " + brokenA.equals(brokenB));
        System.out.println("broken same hash: "
                + (brokenA.hashCode() == brokenB.hashCode()));
        System.out.println("broken add A: " + broken.add(brokenA));
        System.out.println("broken add B: " + broken.add(brokenB));
        System.out.println("broken size: " + broken.size());

        Set<CollidingKey> collision = new HashSet<>();
        System.out.println("collision first: "
                + collision.add(new CollidingKey("A")));
        System.out.println("collision different: "
                + collision.add(new CollidingKey("B")));
        System.out.println("collision equal copy: "
                + collision.add(new CollidingKey("A")));
        System.out.println("collision size: " + collision.size());

        MutableKey mutable = new MutableKey(1);
        Set<MutableKey> mutableSet = new HashSet<>();
        mutableSet.add(mutable);
        System.out.println("mutable before: " + mutableSet.contains(mutable));
        mutable.setId(2); // Đổi cả equals/hash sau khi thêm vào set.
        System.out.println("mutable after: " + mutableSet.contains(mutable));

        Set<Book> withDuplicates = new HashSet<>(
                List.of(first, equalBook, differentBook));
        System.out.println("from list size: " + withDuplicates.size());
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac HashSetEqualityDemo.java
java HashSetEqualityDemo
~~~

Kết quả trên Java 17:

~~~text
same reference: false
equal value: true
equal hash: true
add first: true
add equal: false
size after equal: 1
add different: true
size after different: 2
contains equal copy: true
broken equals: true
broken same hash: false
broken add A: true
broken add B: true
broken size: 2
collision first: true
collision different: true
collision equal copy: false
collision size: 2
mutable before: true
mutable after: false
from list size: 2
~~~

**Giải thích các kết quả:**

1. Hai `Book` khác instance (`== false`), nhưng `equals true` và hash bằng nhau. Vì vậy lần thêm thứ hai trả `false`; set chỉ có một `Book("978-1", "Java")`. `contains` với **instance thứ ba** có cùng giá trị cũng trả `true`.
2. `differentBook` có ISBN và tên khác nên thêm thành công, đưa `size` lên 2.
3. `BrokenKey`: hai khóa có cùng ID nên `equals true`, nhưng hash là 1 và 2. Ở trường hợp cụ thể trên Java 17, chúng được đưa vào hai vị trí băm khác nhau; cả hai lần `add` trả `true` và `size == 2`. Đây là **triển khai sai**, không phải cách đạt được chức năng lưu trùng.
4. `CollidingKey`: cả `"A"` và `"B"` cùng hash nhưng `equals false` nên vẫn là hai phần tử hợp lệ. Một `"A"` khác có cùng giá trị bị từ chối. Hash trùng **không** đồng nghĩa object trùng.
5. `MutableKey`: sau khi thêm với `id = 1`, object bị đổi thành `id = 2`. Trong ví dụ Java 17 này, `contains(mutable)` trả `false` vì vị trí tra cứu theo hash mới không khớp vị trí ghi ban đầu. Hành vi tra cứu khi sửa key như vậy không còn đáng tin cậy.
6. Constructor nhận collection `new HashSet<>(List.of(...))` cũng loại bản sao logic theo equality/hash hợp lệ. Khác nhau ở cú pháp tạo set; quy tắc trùng lặp không đổi.

**Không dựa vào thứ tự phần tử khi in `HashSet`:** tập hợp này không bảo đảm thứ tự duyệt theo thứ tự thêm, theo hash hay theo thứ tự tăng dần. Ví dụ in các giá trị boolean, kích thước và kết quả `contains`, thay vì in nguyên `HashSet` rồi khẳng định một thứ tự cụ thể.

## 5. Vậy thêm hai đối tượng bằng nhau có “mất” dữ liệu không?

Điều cần phân biệt là **instance** và **giá trị phần tử**.

~~~java
Book first = new Book("978-1", "Java");
Book second = new Book("978-1", "Java");

Set<Book> books = new HashSet<>();
books.add(first);   // true
books.add(second);  // false
~~~

Trong ví dụ này, `HashSet` chỉ lưu một đại diện cho **lớp tương đương** gồm các object mà `equals` coi là bằng nhau. Nó không lưu hai bản ghi trùng chỉ để nhớ rằng có hai lần `new`.

Khi `add(second)` trả `false`, **phần tử cũ vẫn nằm trong set**; `second` không được dùng để thay thế `first`. Trong cấu trúc dữ liệu, một phần tử có thể đại diện cho nhiều object bằng nhau theo quy tắc equality; set không hứa sẽ lưu số lần xuất hiện.

Nếu bài toán cần **ghi nhận từng lần xuất hiện**, chọn `List` hoặc collection phù hợp. Nếu cần **đếm số lần**, dùng một map đếm theo giá trị, ví dụ `Map<Book, Integer>` với `merge(book, 1, Integer::sum)`. Nếu cần **chọn object mới thay object cũ**, phải tự định nghĩa nghiệp vụ thay thế; `HashSet.add` không cung cấp hành vi đó.

## 6. Điều gì xảy ra nếu chỉ cùng dữ liệu nhưng `equals()` chưa được ghi đè?

Xét một lớp tự tạo chỉ có constructor và trường `id`:

~~~java
final class PlainItem {
    private final int id;

    PlainItem(int id) {
        this.id = id;
    }
}
~~~

Đây là định nghĩa lớp có thể biên dịch; nó không chứa `main`. Khi thêm `new PlainItem(42)` hai lần, `PlainItem` thừa hưởng `Object.equals()`, vốn dùng identity. Vì vậy hai instance khác nhau **không được xem là bằng nhau**, dù cùng `id = 42`. Một `HashSet<PlainItem>` thường có kích thước 2 sau hai lần thêm.

Đó **không phải lỗi của `HashSet`**: lớp đã định nghĩa equality mặc định là cùng instance. Nếu khái niệm nghiệp vụ yêu cầu hai item cùng ID là một, cần định nghĩa `equals()` theo ID và viết `hashCode()` nhất quán, hoặc dùng value type như record khi phù hợp.

Cũng cần nhớ: ghi đè `equals` theo **chỉ một số trường** nghĩa là các trường còn lại không quyết định trùng lặp. Ví dụ nếu `Book.equals()` chỉ xét ISBN, hai cuốn cùng ISBN nhưng có tên mô tả khác cũng được xem là một phần tử. Định nghĩa equality là quyết định **mô hình dữ liệu**, không phải chi tiết cú pháp.

## 7. Vì sao `hashCode()` sai làm hai object bằng nhau cùng tồn tại?

Giả sử:

- `a.equals(b) == true`.
- `a.hashCode() == 1` nhưng `b.hashCode() == 2`.

Đây là mâu thuẫn trực tiếp với hợp đồng Java. Dù `equals` nói chúng bằng nhau, bước định vị dựa trên hash có thể đưa chúng đến các vùng khác nhau, dẫn đến **không kiểm tra equality với phần tử đã có**. Khi ấy set có thể lưu cả `a` và `b`. Tùy kiểu va chạm, dung lượng và cách cài đặt, kết quả lỗi có thể biến thiên; không nên dùng nó như một quy tắc chức năng được bảo đảm.

Cách khắc phục là:

1. Quyết định rõ những trường nào xác định hai object bằng nhau.
2. Triển khai `equals()` theo đúng các trường đó, tuân thủ phản xạ, đối xứng, bắc cầu và nhất quán.
3. Triển khai `hashCode()` từ **cùng dữ liệu có liên quan** để mọi cặp bằng nhau chắc chắn có hash bằng nhau. Hash không cần duy nhất.
4. Ưu tiên bất biến cho những trường ảnh hưởng equality/hash của phần tử khi nằm trong `HashSet`.
5. Kiểm tra bằng ví dụ tạo hai instance khác nhau có giá trị bằng nhau; xác minh `equals`, mã băm, `add`, `size`, `contains`.

### Mẫu lớp giá trị tự viết

~~~java
import java.util.Objects;

final class ProductCode {
    private final String code;

    ProductCode(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductCode p)) return false;
        return code.equals(p.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

Trong ví dụ này, `ProductCode` là `final` và `code` bất biến. Hai instance có cùng `code` bằng nhau và có cùng hash; cách kiểm tra `instanceof` an toàn với vấn đề lớp con bổ sung trạng thái vì **không thể kế thừa từ lớp `final`**. Chương trình sử dụng lớp này cần cung cấp `main` nếu muốn chạy độc lập.

## 8. Trường hợp `null`, collision và cùng tham chiếu

### Thêm `null` hai lần

`HashSet` cho phép **một phần tử `null`**. Với set ban đầu trống:

~~~java
Set<String> names = new HashSet<>();
System.out.println(names.add(null)); // true
System.out.println(names.add(null)); // false
System.out.println(names.size());    // 1
~~~

Đoạn này đặt trong `main` và cần `import java.util.Set;` cùng `import java.util.HashSet;`. `null` thứ hai không làm tăng kích thước. Không gọi `null.equals(...)`; cấu trúc xử lý `null` theo cách riêng.

### Thêm cùng một instance hai lần

Nếu `Book book = new Book(...)` và gọi `set.add(book)` hai lần, kết quả là `true` rồi `false`. Không cần hai instance riêng để minh họa tính duy nhất; ngay cả cùng một tham chiếu cũng không được ghi hai lần. Điều đó không chứng minh rằng `==` là tiêu chí duy nhất của set.

### Hai object khác nhau nhưng hash giống nhau

Không có yêu cầu rằng hai object khác nhau phải có mã băm khác nhau. Một `hashCode()` luôn trả `7` về mặt **tính đúng** vẫn có thể hợp đồng, vì mọi cặp bằng nhau đều nhận 7; tuy nhiên phân phối hash kém làm nhiều collision, có thể khiến hiệu năng giảm. `HashSet` vẫn cần dùng `equals()` để phân biệt những object **không** bằng nhau.

## 9. Các hệ quả thường gặp khi dùng `HashSet`

**Thứ tự:** `HashSet` không có cam kết về thứ tự duyệt. Nếu muốn thứ tự chèn, cân nhắc `LinkedHashSet`; nếu muốn thứ tự sắp xếp, cân nhắc `TreeSet`, nhưng `TreeSet` coi `compare(...) == 0` là trùng phần tử theo comparator, có thể khác `equals()`.

**Đồng thời:** `HashSet` thông thường không tự đồng bộ. Nếu nhiều thread cùng thay đổi set, cần phương án phối hợp/collection phù hợp; điều này độc lập với hợp đồng equality.

**Không đổi trường dùng làm khóa:** Nếu một phần tử đã được thêm mà các trường dùng để tính hash thay đổi, `contains`, `remove` hay `add` sau đó có thể cho kết quả khó đoán. Đặc biệt, `equals()` và `hashCode()` đúng ở từng thời điểm chưa đủ: tính ổn định của khóa **trong suốt thời gian nằm trong set** cũng quan trọng.

**Giới hạn của kiểm tra bằng kích thước:** Một set có kích thước 1 sau hai lần thêm chỉ chứng minh rằng theo cơ chế equality hiện tại, lần thêm thứ hai không tạo phần tử mới; không tự chứng minh rằng hai object trùng dữ liệu theo mọi tiêu chí nghiệp vụ. Ngược lại, kích thước 2 có thể xuất phát từ định nghĩa equality khác mong đợi hoặc hợp đồng hash bị phá.

## 10. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Hai object trông giống nhau nhưng `size == 2` | Không override `equals`, hoặc `equals` xét thêm trường | In/kiểm tra `equals`; xác định các trường quyết định giá trị |
| `equals == true` nhưng vẫn thêm được cả hai | `hashCode` sai hợp đồng | Kiểm tra hash của cặp bằng nhau; sửa hash nhất quán |
| Hai object khác nhau cùng hash bị coi là một | `equals` triển khai quá rộng hoặc sai | Hash collision **không** đủ để loại trùng; sửa equality |
| `contains` không tìm thấy object đã thêm | Trường hash/equality bị thay đổi hoặc hợp đồng hỏng | Dùng khóa bất biến; tránh sửa trường định danh khi đã thêm |
| Mong phần tử mới thay phần tử cũ khi `add` trùng | Hiểu sai `HashSet.add` | `add` trả `false` và giữ phần tử cũ |
| Kết quả hiển thị mỗi lần in set khác thứ tự | `HashSet` không bảo đảm thứ tự duyệt | Chỉ dựa vào membership/`size`; chọn collection có thứ tự nếu cần |
| Tưởng record so sánh sâu array | Component array vẫn dùng equality của array | Thiết kế riêng nếu muốn so từng phần tử, hoặc thay cấu trúc dữ liệu |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `a != b` theo tham chiếu, `a.equals(b)` là `true`, hash của hai đối tượng bằng nhau. Thêm `a` rồi `b` vào một `HashSet` ban đầu trống có kết quả gì?  
**Đáp án:** `add(a)` trả `true`, `add(b)` trả `false`, kích thước là 1.

**Câu 2.** Hai object có `hashCode() == 7`, nhưng `equals() == false`. `HashSet` có giữ được cả hai không?  
**Đáp án:** Có; hash collision không đồng nghĩa equality. Khi phần tử khác nhau theo equality và hợp đồng hợp lệ, set có thể giữ cả hai.

**Câu 3.** Hai object được ứng dụng coi là bằng nhau nhưng `hashCode()` khác nhau. Nên làm gì?  
**Đáp án:** Sửa lớp để tuân thủ hợp đồng: những object bằng nhau bắt buộc có mã băm giống nhau. Không dựa vào hành vi tình cờ của `HashSet` khi hợp đồng bị vi phạm.

**Câu 4.** Nếu `HashSet.add(second)` trả `false`, set có tự thay `first` thành `second` không?  
**Đáp án:** Không. Phần tử tương đương đã tồn tại được giữ lại.

**Câu 5.** Dùng `new HashSet<>(list)` có loại được bản sao logic trong `list` không?  
**Đáp án:** Có, theo định nghĩa `equals()`/`hashCode()` của phần tử và giả sử hợp đồng được giữ đúng.

**Ghi nhớ:** Thêm hai object **bằng nhau theo `equals()` và có `hashCode()` hợp lệ** vào `HashSet` thì chỉ một phần tử được giữ. Hãy kiểm tra `add` trả `true` hay `false`, cùng `size()`, thay vì dựa vào `==` hoặc thứ tự in ra của tập hợp.
